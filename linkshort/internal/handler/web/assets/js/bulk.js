(function() {
  initKeyBanner();
  setActiveNav("bulk");

  var input = document.getElementById("bulk-input");
  var form = document.getElementById("bulk-form");
  var submitBtn = document.getElementById("bulk-submit");
  var errSpan = document.getElementById("bulk-err");
  var resultPanel = document.getElementById("bulk-result");
  var summaryEl = document.getElementById("bulk-summary");
  var tbody = document.getElementById("bulk-rows");
  var copyAllBtn = document.getElementById("copy-all");
  var passwordEl = document.getElementById("bulk-password");

  var allSuccessLinks = [];
  var rawUrls = [];
  var sentPw = [];

  form.addEventListener("submit", function(e) {
    e.preventDefault();
    errSpan.textContent = "";
    resultPanel.hidden = true;
    allSuccessLinks = [];
    sentPw = [];

    var sharedPassword = passwordEl ? passwordEl.value : "";
    var text = input.value;
    var lines = text.split("\n");
    var items = [];
    rawUrls = [];

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      if (!line) continue;
      var match = line.match(/^(\S+)(?:\s+(\S+))?(?:\s+(\S+))?/);
      if (!match) continue;
      var url = match[1];
      var slug = match[2] || "";
      var pw = match[3] || "";
      var item = { url: url };
      if (slug) item.slug = slug;
      if (pw) item.password = pw;
      else if (sharedPassword) item.password = sharedPassword;
      sentPw.push(!!item.password);
      items.push(item);
      rawUrls.push(url);
    }

    if (rawUrls.length === 0) {
      errSpan.textContent = "请先粘贴至少一条 URL";
      return;
    }

    if (rawUrls.length > 100) {
      errSpan.textContent = "一次最多 100 条";
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "生成中…";

    api("/api/links/batch", { method: "POST", body: items }).then(function(data) {
      submitBtn.disabled = false;
      submitBtn.textContent = "批量生成短链";

      var okCount = data.ok_count;
      var total = data.total;
      var failCount = total - okCount;

      summaryEl.textContent = "成功 " + okCount + " / 失败 " + failCount + " / 共 " + total;

      tbody.innerHTML = "";
      allSuccessLinks = [];

      for (var i = 0; i < data.items.length; i++) {
        var item = data.items[i];
        var tr = document.createElement("tr");

        var tdIdx = document.createElement("td");
        tdIdx.textContent = item.index + 1;
        tr.appendChild(tdIdx);

        var tdUrl = document.createElement("td");
        var urlText = rawUrls[item.index] || "";
        if (item.ok) {
          tdUrl.innerHTML = '<span class="mono">' + esc(urlText) + '</span>';
        } else {
          tdUrl.innerHTML = '<span class="mono">' + esc(urlText) + '</span><br>' + esc(item.error || "");
        }
        tr.appendChild(tdUrl);

        var tdLink = document.createElement("td");
        if (item.ok && item.short_url) {
          var shortUrl = item.short_url;
          tdLink.innerHTML = '<a class="mono" href="' + esc(shortUrl) + '" target="_blank" rel="noopener">' + esc(shortUrl) + '</a>';
          allSuccessLinks.push(shortUrl);
        } else if (item.ok) {
          tdLink.textContent = "—";
        } else {
          tdLink.textContent = "—";
        }
        tr.appendChild(tdLink);

        var tdPw = document.createElement("td");
        tdPw.textContent = (item.ok && sentPw[item.index]) ? "已设" : "—";
        tr.appendChild(tdPw);

        var tdStatus = document.createElement("td");
        if (item.ok) {
          tdStatus.innerHTML = '<span class="badge ok">成功</span>';
        } else {
          tdStatus.innerHTML = '<span class="badge bad">失败</span>';
        }
        tr.appendChild(tdStatus);

        tbody.appendChild(tr);
      }

      resultPanel.hidden = false;
    }).catch(function(err) {
      submitBtn.disabled = false;
      submitBtn.textContent = "批量生成短链";
      errSpan.textContent = err.message || "请求失败";
      resultPanel.hidden = true;
    });
  });

  copyAllBtn.addEventListener("click", function() {
    if (allSuccessLinks.length === 0) {
      toast("没有可复制的短链");
      return;
    }
    copyText(allSuccessLinks.join("\n"));
  });
})();