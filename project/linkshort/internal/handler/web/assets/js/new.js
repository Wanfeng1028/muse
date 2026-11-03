// 新建短链页面逻辑（new.html）
(function () {
  initKeyBanner();
  setActiveNav("new");

  var form = document.getElementById("new-form");
  var urlEl = document.getElementById("url");
  var slugEl = document.getElementById("slug");
  var titleEl = document.getElementById("title");
  var expiresEl = document.getElementById("expires");
  var errEl = document.getElementById("form-err");
  var submitBtn = document.getElementById("submit-btn");
  var resultPanel = document.getElementById("result-panel");
  var resultShort = document.getElementById("result-short");
  var copyResult = document.getElementById("copy-result");
  var resultQr = document.getElementById("result-qr");
  var maxVisitsEl = document.getElementById("max-visits");
  var burnEl = document.getElementById("burn");
  var purgeEl = document.getElementById("purge");
  var passwordEl = document.getElementById("password");

  if (!form) return;

  if (burnEl && maxVisitsEl) {
    burnEl.addEventListener("change", function () {
      maxVisitsEl.disabled = burnEl.checked;
      if (burnEl.checked) {
        maxVisitsEl.value = "";
      }
      if (purgeEl) {
        purgeEl.disabled = !burnEl.checked;
        if (!burnEl.checked) purgeEl.checked = false;
      }
    });
  }
  if (burnEl && purgeEl) {
    purgeEl.disabled = !burnEl.checked;
    if (!burnEl.checked) purgeEl.checked = false;
  }




  form.addEventListener("submit", function (e) {
    e.preventDefault();

    // 清空错误
    if (errEl) { errEl.textContent = ""; errEl.style.display = "none"; }

    var url = urlEl ? urlEl.value.trim() : "";
    if (!url) {
      showErr("请填写目标 URL");
      return;
    }

    // 组装请求体
    var body = { url: url };
    if (slugEl && slugEl.value.trim()) body.slug = slugEl.value.trim();
    if (titleEl && titleEl.value.trim()) body.title = titleEl.value.trim();
    if (expiresEl && expiresEl.value) {
      var d = new Date(expiresEl.value);
      if (!isNaN(d.getTime())) {
        body.expires_at = d.toISOString();
      }
    }

    if (maxVisitsEl && !maxVisitsEl.disabled && maxVisitsEl.value) {
      var mv = parseInt(maxVisitsEl.value, 10);
      if (mv >= 1) body.max_visits = mv;
    }
    if (burnEl && burnEl.checked) {
      body.burn = true;
    }
    if (purgeEl && purgeEl.checked && burnEl && burnEl.checked) {
      body.purge = true;
    }
    if (passwordEl && passwordEl.value) {
      body.password = passwordEl.value;
    }




    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = "生成中…";
    }

    api("/api/links", {
      method: "POST",
      body: body
    }).then(function (data) {
      data = data || {};
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = "生成短链";
      }
      // 显示结果
      if (resultPanel) resultPanel.hidden = false;
      if (resultShort) {
        resultShort.textContent = data.short_url || "";
        resultShort.href = data.short_url || "#";
      }
      if (resultQr) {
        resultQr.src = "/api/links/" + encodeURIComponent(data.id) + "/qrcode.png?size=200&key=" + encodeURIComponent(API_KEY);
      }
      toast("短链已生成");
    }).catch(function (err) {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = "生成短链";
      }
      showErr(err.message || "生成失败");
    });
  });

  // 复制结果短地址
  if (copyResult) {
    copyResult.addEventListener("click", function () {
      if (resultShort) copyText(resultShort.textContent || "");
    });
  }

  function showErr(msg) {
    if (errEl) {
      errEl.textContent = msg;
      errEl.style.display = "";
    } else {
      toast(msg);
    }
  }
})();
