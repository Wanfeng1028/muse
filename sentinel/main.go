package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"flag"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"sentinel/internal/backup"
	"sentinel/internal/config"
	"sentinel/internal/db"
	"sentinel/internal/escalation"
	"sentinel/internal/handlers"
	"sentinel/internal/log"
	"sentinel/internal/metrics"
	"sentinel/internal/notify"
	"sentinel/internal/scheduler"
	"sentinel/internal/seed"
	"sentinel/internal/store"
)

func main() {
	// 命令行参数：备份恢复路径
	restorePath := flag.String("restore", "", "从指定备份文件恢复数据库")
	flag.Parse()

	// 加载配置
	cfg, err := config.Load()
	if err != nil {
		fmt.Fprintln(os.Stderr, "加载配置失败:", err)
		os.Exit(1)
	}

	// 初始化日志
	log.Init(cfg.LogLevel)
	logger := log.Logger()

	// 恢复模式：在打开数据库之前执行
	if *restorePath != "" {
		if err := backup.Restore(cfg.DBPath, *restorePath); err != nil {
			logger.Error("数据库恢复失败", "err", err, "path", *restorePath)
			os.Exit(1)
		}
		logger.Info("数据库恢复成功", "path", *restorePath)
		os.Exit(0)
	}

	// 打开数据库
	sqlDB, err := db.Open(cfg.DBPath)
	if err != nil {
		logger.Error("打开数据库失败", "err", err, "path", cfg.DBPath)
		os.Exit(1)
	}
	defer sqlDB.Close()

	// 初始化存储层
	st := store.New(sqlDB)
	if err := st.EnsureDefaultTenant(); err != nil {
		logger.Error("初始化默认租户失败", "err", err)
		os.Exit(1)
	}

	// 若没有任何用户且配置了 APIToken，创建默认 admin 用户
	users, _ := st.ListUsers()
	if len(users) == 0 && cfg.APIToken != "" {
		sum := sha256.Sum256([]byte(cfg.APIToken))
		hash := hex.EncodeToString(sum[:])
		if _, err := st.CreateUser(1, "admin", hash); err != nil {
			logger.Error("创建默认 admin 用户失败", "err", err)
			os.Exit(1)
		}
		logger.Info("已创建默认 admin 用户")
	}

	// 通知器封装
	// 短信发送器：mock 模式内存记录不真发，aliyun/tencent 模式走对应云短信；构造失败（未配置）直接退出。
	smsCfg := notify.SMSConfig{
		Mode:   cfg.SMSMode,
		Phones: cfg.SMSPhones,
		Aliyun: notify.AliyunConfig{
			AccessKeyID:     cfg.SMSAccessKeyID,
			AccessKeySecret: cfg.SMSAccessKeySecret,
			SignName:        cfg.SMSSignName,
			TemplateCode:    cfg.SMSTemplateCode,
		},
		Tencent: notify.TencentConfig{
			SecretId:    cfg.SMSTencentSecretID,
			SecretKey:   cfg.SMSTencentSecretKey,
			SmsSdkAppId: cfg.SMSTencentSdkAppID,
			SignName:    cfg.SMSTencentSignName,
			TemplateId:  cfg.SMSTencentTemplateID,
			Region:      cfg.SMSTencentRegion,
			Endpoint:    cfg.SMSTencentEndpoint,
		},
	}
	smsSender, err := smsCfg.BuildSender()
	if err != nil {
		logger.Error("初始化短信通道失败", "err", err)
		os.Exit(1)
	}
	ntf := notify.Notifier{
		WebhookURL: cfg.WebhookURL,
		SMTP: notify.SMTPConfig{
			Host:     cfg.SMTPHost,
			Port:     cfg.SMTPPort,
			Username: cfg.SMTPUsername,
			Password: cfg.SMTPPassword,
			From:     cfg.SMTPFrom,
			To:       cfg.SMTPTo,
		},
		WeCom: notify.WeComConfig{
			WebhookURL: cfg.WeComWebhookURL,
			MentionAll: cfg.WeComMentionAll,
		},
		Channels:  cfg.NotifyChannels,
		SMS:       smsCfg,
		SMSSender: smsSender,
	}

	subMailer := notify.SMTPMailer{Notifier: notify.SMTPNotifier{Config: ntf.SMTP}}
	// webhook 投递队列：告警产生时只入队，由 worker 按指数退避重投
	queueSender := &notify.QueueSender{
		Store:          st,
		MaxAttempts:    cfg.QueueMaxAttempts,
		BaseBackoffSec: int64(cfg.QueueBaseBackoffSec),
		TickSec:        cfg.QueueTickSec,
	}
	queueSender.Limiter = notify.NewRateLimiter(cfg.QueueEnqueueRPS, cfg.QueueEnqueueBurst)
	if queueSender.Limiter == nil {
		logger.Info("webhook 入队限流已禁用")
	} else {
		logger.Info("webhook 入队限流已启用", "rps", cfg.QueueEnqueueRPS, "burst", cfg.QueueEnqueueBurst)
	}

	queueSender.Breakers = notify.NewBreakerRegistry(cfg.BreakerFailureThreshold, time.Duration(cfg.BreakerOpenTimeoutSec)*time.Second)
	logger.Info("webhook 投递熔断已启用", "failure_threshold", cfg.BreakerFailureThreshold, "open_timeout_sec", cfg.BreakerOpenTimeoutSec)

	ntf.Queue = queueSender

	notifyFn := func(m store.Monitor, event, name, target, at, errMsg string) {
		errs := ntf.Notify(notify.Target{MonitorID: m.ID, WebhookURL: m.WebhookURL, NotifyChannels: m.NotifyChannels, SMSPhones: m.SMSPhones}, event, name, target, at, errMsg)
		if serr := notify.NotifySubscribers(st, subMailer, cfg.PublicURL, m.ID, event, name, target, at, errMsg); serr != nil {
			errs = append(errs, serr)
		}
		metrics.Default.RecordWebhook(len(errs) == 0)
	}

	// 信号上下文
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// 备份循环
	go func() {
		// 立即执行一次备份
		if _, err := backup.Backup(cfg.DBPath, cfg.BackupDir, cfg.BackupKeep); err != nil {
			logger.Error("备份失败", "err", err)
		} else {
			logger.Info("备份完成")
		}
		// 若未配置间隔则仅执行一次
		if cfg.BackupIntervalH <= 0 {
			return
		}
		ticker := time.NewTicker(time.Duration(cfg.BackupIntervalH) * time.Hour)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if _, err := backup.Backup(cfg.DBPath, cfg.BackupDir, cfg.BackupKeep); err != nil {
					logger.Error("备份失败", "err", err)
				} else {
					logger.Info("备份完成")
				}
			}
		}
	}()

	// 启动调度器
	sch := scheduler.New(st, notifyFn, cfg.CheckConcurrency, cfg.SchedulerTickSec, cfg.CheckRetryMax)
	if len(cfg.Escalation) > 0 {
		levels := make([]escalation.Level, 0, len(cfg.Escalation))
		for _, l := range cfg.Escalation {
			levels = append(levels, escalation.Level{AfterMinutes: l.AfterMinutes, Channels: l.Channels})
		}
		sch.SetEscalation(levels)
		logger.Info("告警升级已启用", "levels", len(levels))
	}
	go sch.Start(ctx)

	// 启动 webhook 投递队列 worker
	go queueSender.Run(ctx)
	// 初始化种子数据
	seed.EnsureSeed(st)

	// HTTP 服务
	h := handlers.New(st, sch, cfg.CheckRetryMax)
	h.SetMailer(subMailer)
	// 快照定时生成：调度器扫描回调复用 handler 的生成归档链路
	sch.SetSnapshotGenerator(func(pageID int64) error {
		_, err := h.GenerateAndStoreSnapshot(pageID, "schedule")
		return err
	})
	h.SetPublicURL(cfg.PublicURL)
	h.SetQueueSender(queueSender)
	srv := &http.Server{
		Addr:         cfg.Addr(),
		Handler:      h.Routes(),
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}
	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("HTTP 服务异常退出", "err", err)
		}
	}()

	// 等待退出信号
	<-ctx.Done()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		logger.Error("优雅关闭失败", "err", err)
	}
	logger.Info("服务已优雅关闭")
}
