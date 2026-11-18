/* Мобильное меню, автоскрытие сообщений и предварительный расчёт цены. */
document.addEventListener("DOMContentLoaded", function () {
  var burger = document.querySelector(".burger");
  var menu = document.querySelector(".menu");
  if (burger && menu) {
    burger.addEventListener("click", function () {
      menu.classList.toggle("open");
      burger.setAttribute("aria-expanded", menu.classList.contains("open") ? "true" : "false");
    });
  }

  var messages = document.querySelectorAll(".message");
  if (messages.length) {
    setTimeout(function () {
      messages.forEach(function (node) {
        node.style.transition = "opacity .4s ease";
        node.style.opacity = "0";
        setTimeout(function () { node.remove(); }, 420);
      });
    }, 7000);
  }

  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  var priceBox = document.querySelector("[data-calc]");
  if (priceBox) {
    var base = parseFloat(priceBox.dataset.basePrice) || 0;
    var urgentRate = parseFloat(priceBox.dataset.urgentRate) || 1;
    var distanceRate = parseFloat(priceBox.dataset.distanceRate) || 1;
    var urgentInput = document.querySelector("[name=urgent]");
    var distanceInput = document.querySelector("[name=distance_km]");
    var output = document.querySelector("[data-price-output]");

    function format(value) {
      return value.toLocaleString("ru-RU", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    }

    function recalc() {
      var total = base;
      if (urgentInput && urgentInput.checked) { total *= urgentRate; }
      var distance = distanceInput ? parseInt(distanceInput.value, 10) || 0 : 0;
      if (distance > 10) { total *= distanceRate; }
      if (total >= 10000) { total *= 0.95; }
      if (output) { output.textContent = format(total); }
    }

    if (urgentInput) { urgentInput.addEventListener("change", recalc); }
    if (distanceInput) { distanceInput.addEventListener("input", recalc); }
    recalc();
  }
});
