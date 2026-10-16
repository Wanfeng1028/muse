(function () {
  "use strict";

  var mq = window.matchMedia("(max-width: 768px)");

  function setView(view) {
    if (!mq.matches) return;
    if (view !== "tree" && view !== "list" && view !== "reader") return;
    document.body.setAttribute("data-mobile-view", view);
    var btns = document.querySelectorAll(".mobile-view-btn");
    for (var i = 0; i < btns.length; i++) {
      var b = btns[i];
      if (b.getAttribute("data-view") === view) {
        b.classList.add("is-active");
      } else {
        b.classList.remove("is-active");
      }
    }
  }

  function clearView() {
    document.body.removeAttribute("data-mobile-view");
    var btns = document.querySelectorAll(".mobile-view-btn");
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.remove("is-active");
    }
    var first = document.querySelector('.mobile-view-btn[data-view="tree"]');
    if (first) first.classList.add("is-active");
  }

  function onMqChange() {
    if (mq.matches) {
      var current = document.body.getAttribute("data-mobile-view");
      if (!current) setView("tree");
    } else {
      clearView();
    }
  }

  document.addEventListener("click", function (e) {
    if (!mq.matches) return;

    var viewBtn = e.target.closest ? e.target.closest(".mobile-view-btn") : null;
    if (viewBtn) {
      setView(viewBtn.getAttribute("data-view"));
      return;
    }

    var treeItem = e.target.closest ? e.target.closest(".tree-item") : null;
    if (treeItem) {
      setView("list");
      return;
    }

    var listRoot = document.getElementById("article-list");
    if (listRoot && listRoot.contains(e.target)) {
      var hit = e.target.closest ? e.target.closest("a, button, [data-article]") : null;
      if (hit) {
        setView("reader");
      }
    }
  }, false);

  if (mq.addEventListener) {
    mq.addEventListener("change", onMqChange);
  } else if (mq.addListener) {
    mq.addListener(onMqChange);
  }

  if (mq.matches) {
    setView("tree");
  }
})();
