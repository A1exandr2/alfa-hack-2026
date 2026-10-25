const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require(process.env.CREDIT_JSDOM_PATH || "jsdom");
const source = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");
const product = {
  id: "p1",
  name: "Оборотный кредит",
  description: "На задачи бизнеса",
  min_amount: 100000,
  max_amount: 5000000,
  min_term_months: 6,
  max_term_months: 36,
  interest_rate: 18.9,
};
const company = {
  id: "c1",
  name: "ООО «Проверка»",
  inn: "7701234567",
  status: "Действует",
  data_source: "demo",
};
const user = {
  id: "u1",
  full_name: "Иван Иванов",
  role: "USER",
  company_id: "c1",
};
const financials = {
  revenue_annual: 12000000,
  profit_annual: 2500000,
  expenses_annual: 9500000,
  employees: 24,
  current_debt: 800000,
  source: "demo",
  updated_at: "2026-10-24T12:00:00Z",
};
const application = {
  id: "a1",
  company_id: "c1",
  product_id: "p1",
  requested_amount: "100000",
  term_months: 6,
  purpose: "Оборотные средства",
  status: "DRAFT",
  created_at: "2026-10-24T12:00:00Z",
};
function setup({ hash = "/", token = true, overrides = {}, viewport = null } = {}) {
  const dom = new JSDOM('<div id="app"></div><div id="notice"></div>', {
    url: "http://localhost/#" + hash,
    runScripts: "outside-only",
  });
  const w = dom.window;
  if (viewport) {
    const visualViewport = new w.EventTarget();
    Object.assign(visualViewport, viewport);
    Object.defineProperty(w, 'visualViewport', { value: visualViewport });
  }
  w.scrollTo = () => {};
  Object.defineProperty(w.document, "hidden", { value: false });
  w.HTMLDialogElement.prototype.showModal = function() { this.open = true; };
  w.HTMLDialogElement.prototype.close = function() { this.open = false; this.dispatchEvent(new w.Event("close")); };
  w.AbortController = AbortController;
  if (token) w.sessionStorage.setItem("credit-token", "test-token");
  const calls = [];
  const defaults = {
    "/applications/quote": (options) => {
      const input = JSON.parse(options.body);
      const rate = 18.9,
        n = input.term_months,
        amount = Number(input.requested_amount),
        monthly = rate / 1200;
      const payment = (amount * monthly) / (1 - (1 + monthly) ** -n);
      return {
        ok: true,
        status: 200,
        json: async () => ({
          product_id: "p1",
          product_name: "Оборотный кредит",
          annual_rate: String(rate),
          base_rate: String(rate),
          amount_adjustment: "0",
          term_adjustment: "0",
          rules_version: "demo-v1",
          selection_mode: "AUTO",
          requested_amount: input.requested_amount,
          term_months: n,
          monthly_payment: String(payment),
          total_interest: String(payment * n - amount),
          total_repayment: String(payment * n),
          selection_reason: "Подобран по условиям",
          disclaimer: "Без комиссий и страховок. Демонстрационный расчёт.",
        }),
      };
    },
    "/auth/me": user,
    "/company": company,
    "/credit-products": [product],
    "/applications": [],
    "/company/financials": financials,
    "/company/credit-history": {
      active_credits: 1,
      closed_credits: 2,
      overdue_count: 0,
      overdue_amount: 0,
    },
  };
  w.fetch = async (url, options = {}) => {
    const key = url.replace("/api/v1", "");
    calls.push({ key, ...options });
    const value = Object.hasOwn(overrides, key)
      ? overrides[key]
      : defaults[key];
    if (typeof value === "function") return value(options);
    return {
      ok: value !== undefined,
      status: value === undefined ? 404 : 200,
      json: async () => value ?? { detail: "Not found" },
    };
  };
  w.eval(source + "\nwindow.__loanEstimate = loanEstimate;");
  return { dom, w, calls, root: w.document.querySelector("#app") };
}
async function until(check) {
  for (let i = 0; i < 100; i++) {
    if (check()) return;
    await new Promise((r) => setTimeout(r, 5));
  }
  assert.fail("Timed out waiting for UI");
}
function submit(w, form, button) {
  form.dispatchEvent(
    new w.SubmitEvent("submit", {
      bubbles: true,
      cancelable: true,
      submitter:
        button || form.querySelector("button[type=submit], button:not([type])"),
    }),
  );
}
test("registration form validates fields and does not leak HTML", async () => {
  const { dom, w, root } = setup({ token: false, hash: "/register" });
  await until(() => root.querySelector('[data-form="register"]'));
  assert.equal(root.querySelector("[name=password]").minLength, 8);
  assert.ok(root.textContent.includes("Создайте аккаунт"));
  assert.equal(w.document.querySelectorAll("script").length, 0);
  dom.window.close();
});
test("new account sees INN onboarding when company is missing", async () => {
  const { dom, root } = setup({
    hash: "/company",
    overrides: { "/company": undefined },
  });
  await until(() => root.querySelector('[data-form="link"]'));
  assert.equal(
    root.querySelector("[name=inn]").pattern,
    "[0-9]{10}([0-9]{2})?",
  );
  dom.window.close();
});
test("dashboard renders API values and escapes company HTML", async () => {
  const { dom, w, root } = setup({
    overrides: {
      "/company": { ...company, name: "<img src=x onerror=alert(1)>" },
    },
  });
  await until(() => root.querySelector(".metrics"));
  assert.match(root.textContent, /12\s000\s000/);
  assert.equal(root.querySelectorAll("img").length, 0);
  assert.ok(root.textContent.includes("<img src=x"));
  assert.equal(w.sessionStorage.getItem("credit-token"), "test-token");
  dom.window.close();
});
test("login errors remain in the form and allow retry", async () => {
  const { dom, w, root } = setup({
    token: false,
    hash: "/login",
    overrides: {
      "/auth/login": () => ({
        ok: false,
        status: 401,
        json: async () => ({ detail: "Invalid email or password" }),
      }),
    },
  });
  const form = root.querySelector("form");
  form.elements.email.value = "wrong@example.com";
  form.elements.password.value = "wrong";
  submit(w, form);
  await until(() => form.querySelector(".error"));
  assert.match(form.textContent, /Неверная почта/);
  assert.equal(form.querySelector("button[type=submit]").disabled, false);
  dom.window.close();
});
test("application saves real payload as draft without invoking LLM", async () => {
  const { dom, w, root, calls } = setup({
    hash: "/new/p1",
    overrides: {
      "/applications": (options) => ({
        ok: true,
        status: 200,
        json: async () => (options.method === "POST" ? application : []),
      }),
      "/applications/a1": application,
      "/applications/a1/history": [],
    },
  });
  await until(() =>
    root.querySelector("[data-form=application][data-quote-ready=true]"),
  );
  const form = root.querySelector("form");
  form.elements.purpose.value = "Закупка оборудования";
  const draft = form.querySelector("[value=draft]");
  submit(w, form, draft);
  await until(() =>
    calls.some((c) => c.key === "/applications" && c.method === "POST"),
  );
  const call = calls.find(
    (c) => c.key === "/applications" && c.method === "POST",
  );
  assert.deepEqual(JSON.parse(call.body), {
    requested_amount: "100000",
    term_months: 6,
    purpose: "Закупка оборудования",
    additional_info: "",
    purpose_category: "other",
  });
  assert.equal(
    calls.some((c) => c.key.endsWith("/submit")),
    false,
  );
  assert.equal(call.headers.Authorization, "Bearer test-token");
  await until(() => root.textContent.includes("Как движется заявка"));
  dom.window.close();
});
test("submitted application displays AI result and history", async () => {
  let submitted = false;
  const decision = {
    outcome: "CONDITIONAL_APPROVAL",
    source: "AI",
    risk_score: 40,
    risk_level: "Medium",
    explanation: "Нужна проверка документов",
    recommended_product: "Оборотный",
    next_step: "Предоставьте документы",
    top_factors: ["Долговая нагрузка"],
    conditions: ["Подтвердить выручку"],
  };
  const { dom, w, root, calls } = setup({
    hash: "/new/p1",
    overrides: {
      "/applications": (options) => ({
        ok: true,
        status: 200,
        json: async () => (options.method === "POST" ? application : []),
      }),
      "/applications/a1": () => ({
        ok: true,
        status: 200,
        json: async () => ({
          ...application,
          status: submitted ? "MANUAL_REVIEW" : "DRAFT",
        }),
      }),
      "/applications/a1/history": [],
      "/applications/a1/decision": () => ({
        ok: submitted,
        status: submitted ? 200 : 404,
        json: async () => decision,
      }),
      "/applications/a1/submit": () => {
        submitted = true;
        return {
          ok: true,
          status: 200,
          json: async () => ({
            ...application,
            status: "MANUAL_REVIEW",
            decision,
          }),
        };
      },
    },
  });
  await until(() =>
    root.querySelector("[data-form=application][data-quote-ready=true]"),
  );
  const form = root.querySelector("form");
  form.elements.purpose.value = "Закупка товаров";
  submit(w, form, form.querySelector("[value=submit]"));
  await until(() => root.textContent.includes("Нужна проверка документов"));
  assert.ok(root.textContent.includes("Требуется ручная проверка"));
  assert.ok(root.textContent.includes("Подтвердить выручку"));
  assert.ok(calls.some((c) => c.key === "/applications/a1/submit"));
  assert.equal(root.textContent.includes("Принять предложение"), false);
  dom.window.close();
});
test("missing-data workflow shows required fields and editing link", async () => {
  const { dom, root } = setup({
    hash: "/applications/a1",
    overrides: {
      "/applications/a1": { ...application, status: "NEED_MORE_DATA" },
      "/applications/a1/history": [
        {
          event_type: "APPLICATION_DATA_REQUIRED",
          details: { required_fields: ["revenue_annual"] },
          occurred_at: "2026-10-24T12:00:00Z",
        },
      ],
    },
  });
  await until(() => root.textContent.includes("Исправить заявку"));
  assert.ok(root.textContent.includes("Выручка за год"));
  assert.ok(root.querySelector('a[href="#/company/financials"]'));
  dom.window.close();
});
test("review form is available only for reviewer role", async () => {
  const { dom, root } = setup({
    hash: "/applications/a1",
    overrides: {
      "/auth/me": { ...user, role: "REVIEWER" },
      "/applications/a1": { ...application, status: "MANUAL_REVIEW" },
      "/applications/a1/history": [],
    },
  });
  await until(() => root.querySelector("[data-form=review]"));
  assert.equal(root.querySelector("[name=outcome]").value, "APPROVED");
  dom.window.close();
});
test("expired JWT clears session and returns to login", async () => {
  const { dom, w, root } = setup({
    overrides: {
      "/auth/me": () => ({
        ok: false,
        status: 401,
        json: async () => ({
          detail: "Invalid or missing authentication token",
        }),
      }),
    },
  });
  await until(() => root.querySelector("[data-form=login]"));
  assert.equal(w.sessionStorage.getItem("credit-token"), null);
  dom.window.close();
});

test("loan summary follows amount and term input", async () => {
  const { dom, w, root } = setup({ hash: "/new/p1" });
  await until(() =>
    root.querySelector("[data-form=application][data-quote-ready=true]"),
  );
  const input = root.querySelector("[name=requested_amount]");
  input.value = "1500000";
  input.dispatchEvent(new w.Event("input", { bubbles: true }));
  await until(() =>
    /1\s500\s000/.test(root.querySelector(".summary").textContent),
  );
  dom.window.close();
});

test("all sidebar destinations change content before company is linked", async () => {
  const { dom, w, root } = setup({
    hash: "/company",
    overrides: { "/company": undefined },
  });
  await until(() => root.querySelector("[data-form=link]"));
  const routes = [
    ["#/products", "Для следующего шага.", "Кредитные продукты"],
    ["#/applications", "Ваши планы — в работе.", "Мои заявки"],
    ["#/", "Кредитный кабинет для вашего бизнеса.", "Главная"],
    ["#/company", "Познакомимся с вашим бизнесом.", "Компания"],
  ];
  for (const [href, title, label] of routes) {
    root.querySelector(`.nav a[href="${href}"]`).click();
    await until(() => root.querySelector("h1")?.textContent === title);
    assert.equal(
      root.querySelector(".nav [aria-current=page]").textContent.trim(),
      label,
    );
  }
  dom.window.close();
});

test("short registration passwords are blocked before any API call", async () => {
  const { dom, w, root, calls } = setup({ token: false, hash: "/register" });
  const form = root.querySelector("form");
  form.elements.full_name.value = "Test User";
  form.elements.email.value = "test@example.com";
  form.elements.password.value = "abc";
  form.elements.password.dispatchEvent(new w.Event("input", { bubbles: true }));
  assert.match(
    root.querySelector("[data-password-label]").textContent,
    /Ещё 5/,
  );
  assert.equal(form.elements.password.validity.customError, true);
  assert.equal(form.querySelector("button[type=submit]").disabled, true);
  submit(w, form);
  await until(() => form.querySelector(".error"));
  assert.equal(
    calls.some((c) => c.key === "/auth/register"),
    false,
  );
  dom.window.close();
});

test("password feedback distinguishes weak and strong valid passwords", async () => {
  const { dom, w, root } = setup({ token: false, hash: "/register" });
  const input = root.querySelector("[name=password]");
  input.value = "12345678";
  input.dispatchEvent(new w.Event("input", { bubbles: true }));
  assert.equal(
    root.querySelector("[data-password-label]").textContent,
    "Сложность: низкая",
  );
  assert.equal(input.validity.customError, false);
  input.value = "Company!2026Strong";
  input.dispatchEvent(new w.Event("input", { bubbles: true }));
  assert.equal(
    root.querySelector("[data-password-label]").textContent,
    "Сложность: высокая",
  );
  assert.equal(root.querySelector("button[type=submit]").disabled, false);
  dom.window.close();
});

test("password eye toggles visibility in login and registration without submitting", async () => {
  for (const hash of ["/login", "/register"]) {
    const { dom, root, calls } = setup({ token: false, hash });
    const input = root.querySelector("[name=password]");
    const toggle = root.querySelector("[data-action=toggle-password]");
    input.value = "Example!2026";
    assert.equal(input.type, "password");
    toggle.click();
    assert.equal(input.type, "text");
    assert.equal(toggle.getAttribute("aria-label"), "Скрыть пароль");
    assert.equal(toggle.getAttribute("aria-pressed"), "true");
    toggle.click();
    assert.equal(input.type, "password");
    assert.equal(input.value, "Example!2026");
    assert.equal(toggle.getAttribute("aria-label"), "Показать пароль");
    assert.equal(calls.length, 0);
    dom.window.close();
  }
});

test("company onboarding preserves chosen product and continues through finances", async () => {
  let linked = false;
  const { dom, w, root } = setup({
    hash: "/new/p1",
    overrides: {
      "/company": () => ({
        ok: linked,
        status: linked ? 200 : 404,
        json: async () =>
          linked ? company : { detail: "Company is not linked" },
      }),
      "/company/link": () => {
        linked = true;
        return { ok: true, status: 200, json: async () => company };
      },
    },
  });
  await until(() => root.querySelector("h1")?.textContent === "Новая заявка");
  assert.equal(w.sessionStorage.getItem("credit-selected-product"), "p1");
  root.querySelector('.empty a[href="#/company"]').click();
  await until(() => root.querySelector("[data-form=link]"));
  let form = root.querySelector("[data-form=link]");
  form.elements.inn.value = "7701234567";
  submit(w, form);
  await until(() => root.querySelector("[data-form=financials]"));
  assert.match(root.textContent, /Сохранить и продолжить/);
  form = root.querySelector("[data-form=financials]");
  submit(w, form);
  await until(() =>
    root.querySelector("[data-form=application][data-quote-ready=true]"),
  );
  assert.equal(w.location.hash, "#/new");
  assert.equal(w.sessionStorage.getItem("credit-onboarding"), null);
  dom.window.close();
});

test("duplicate email shows Russian guidance and login link", async () => {
  const { dom, w, root } = setup({
    token: false,
    hash: "/register",
    overrides: {
      "/auth/register": () => ({
        ok: false,
        status: 409,
        json: async () => ({ detail: "User with this email already exists" }),
      }),
    },
  });
  const form = root.querySelector("form");
  form.elements.full_name.value = "Test";
  form.elements.email.value = "test@example.com";
  form.elements.password.value = "Example!2026";
  submit(w, form);
  await until(() => form.querySelector(".error-link"));
  assert.match(
    form.querySelector(".error").textContent,
    /Аккаунт с этой почтой уже существует/,
  );
  assert.equal(
    form.querySelector(".error-link").getAttribute("href"),
    "#/login",
  );
  assert.equal(root.textContent.includes("User with this email"), false);
  dom.window.close();
});
test("validation details are translated without technical field paths", async () => {
  const { dom, w, root } = setup({
    token: false,
    hash: "/register",
    overrides: {
      "/auth/register": () => ({
        ok: false,
        status: 422,
        json: async () => ({
          detail: [
            {
              loc: ["body", "email"],
              type: "value_error",
              msg: "Internal validation details",
            },
          ],
        }),
      }),
    },
  });
  const form = root.querySelector("form");
  form.elements.password.value = "Example!2026";
  submit(w, form);
  await until(() => form.querySelector(".error"));
  assert.match(
    form.querySelector(".error").textContent,
    /Электронная почта: проверьте/,
  );
  assert.equal(root.textContent.includes("Internal validation"), false);
  dom.window.close();
});
test("unknown server errors show safe Russian notification", async () => {
  const { dom, w, root } = setup({
    token: false,
    hash: "/login",
    overrides: {
      "/auth/login": () => ({
        ok: false,
        status: 500,
        json: async () => ({
          detail: "SQL exception with internal server details",
        }),
      }),
    },
  });
  const form = root.querySelector("form");
  submit(w, form);
  await until(() => form.querySelector(".error"));
  assert.match(
    form.querySelector(".error").textContent,
    /Сервис временно недоступен/,
  );
  assert.equal(w.document.querySelector("#notice").dataset.kind, "error");
  assert.equal(root.textContent.includes("SQL exception"), false);
  dom.window.close();
});

test("home explains platform without a company and has no duplicate navigation", async () => {
  const { dom, root } = setup({ overrides: { "/company": undefined } });
  await until(() => root.querySelector(".platform-intro"));
  assert.match(root.textContent, /Как работает платформа/);
  assert.ok(root.querySelector('.intro-grid a[href="#/company"]'));
  assert.equal(root.querySelector(".journey"), null);
  assert.equal(root.querySelector('.nav a[href="#/financials"]'), null);
  dom.window.close();
});
test("finances are a company tab and require explicit edit action", async () => {
  const { dom, root } = setup({
    hash: "/company/financials",
    overrides: {
      "/company/financials": { ...financials, source: "USER_VERIFIED" },
    },
  });
  await until(() => root.querySelector("[data-form=financials]"));
  assert.equal(
    root.querySelector(".nav [aria-current=page]").textContent.trim(),
    "Компания",
  );
  assert.ok(
    root.querySelector('.tablinks a.active[href="#/company/financials"]'),
  );
  const input = root.querySelector("[name=revenue_annual]");
  assert.equal(input.readOnly, true);
  root.querySelector("[data-action=edit-financials]").click();
  assert.equal(input.readOnly, false);
  assert.match(root.textContent, /Введено пользователем/);
  dom.window.close();
});
test("unlink requires confirmation and clears only company state", async () => {
  let linked = true;
  const { dom, root, calls } = setup({
    hash: "/company",
    overrides: {
      "/company": (options) => {
        if (options.method === "DELETE") {
          linked = false;
          return { ok: true, status: 204, json: async () => null };
        }
        return {
          ok: linked,
          status: linked ? 200 : 404,
          json: async () => company,
        };
      },
    },
  });
  await until(() => root.querySelector("[data-action=show-unlink]"));
  assert.equal(root.querySelector(".unlink-confirm").hidden, true);
  root.querySelector("[data-action=show-unlink]").click();
  assert.equal(root.querySelector(".unlink-confirm").hidden, false);
  assert.equal(
    calls.some((c) => c.method === "DELETE"),
    false,
  );
  root.querySelector("[data-action=unlink-company]").click();
  await until(() => root.querySelector("[data-form=link]"));
  assert.ok(calls.some((c) => c.key === "/company" && c.method === "DELETE"));
  dom.window.close();
});

test("switching company tabs preserves scroll position", async () => {
  const { dom, w, root } = setup({ hash: "/company" });
  await until(() => root.querySelector(".tablinks"));
  Object.defineProperty(w, "scrollY", { value: 340, configurable: true });
  const scrolls = [];
  w.scrollTo = (options) => scrolls.push(options);
  root.querySelector('.tablinks a[href="#/company/financials"]').click();
  await until(() => root.querySelector("[data-form=financials]"));
  await until(() => scrolls.length > 0);
  assert.equal(scrolls.at(-1).top, 340);
  root.querySelector('.tablinks a[href="#/company"]').click();
  await until(() => root.querySelector("[data-action=show-unlink]"));
  assert.equal(scrolls.at(-1).top, 340);
  dom.window.close();
});

test("application list includes the annual catalog rate", async () => {
  const { dom, root } = setup({
    hash: "/applications",
    overrides: { "/applications": [application] },
  });
  await until(() => root.querySelector("table"));
  assert.match(root.textContent, /Предварительная ставка/);
  assert.match(root.textContent, /18,9% годовых/);
  dom.window.close();
});
test("loan calculator handles monthly repayment and zero interest", async () => {
  const { dom, w, root } = setup({ hash: "/new/p1" });
  await until(() => root.querySelector(".estimate"));
  const normal = w.__loanEstimate(100000, 12, 12);
  assert.ok(Math.abs(normal.payment - 8884.8788678) < 0.01);
  assert.ok(Math.abs(normal.total - 106618.546413) < 0.01);
  assert.equal(w.__loanEstimate(120000, 12, 0).payment, 10000);
  assert.equal(w.__loanEstimate(100000, 0, 12), null);
  assert.match(root.querySelector(".estimate").textContent, /Без комиссий/);
  dom.window.close();
});
test("customer sees price estimates while reviewer can inspect internal scoring", async () => {
  for (const role of ["USER", "REVIEWER"]) {
    const decision = {
      outcome: "APPROVED",
      source: "AI",
      risk_score: 25,
      risk_level: "Low",
      explanation: "Предварительное решение",
      recommended_product: "Оборотный",
      next_step: "Проверьте условия",
      top_factors: ["Внутренний фактор"],
      conditions: [],
    };
    const { dom, root } = setup({
      hash: "/applications/a1",
      overrides: {
        "/auth/me": { ...user, role },
        "/applications/a1": { ...application, status: "DECISION" },
        "/applications/a1/history": [],
        "/applications/a1/decision": decision,
      },
    });
    await until(() => root.textContent.includes("Ставка по каталогу"));
    assert.equal(root.textContent.includes("25 / 100"), role === "REVIEWER");
    assert.equal(
      root.textContent.includes("Внутренний фактор"),
      role === "REVIEWER",
    );
    assert.match(root.textContent, /18,9% годовых/);
    dom.window.close();
  }
});

test("every product card opens the same form without fixing product", async () => {
  const { dom, root } = setup({ hash: "/products" });
  await until(() => root.querySelector(".product"));
  for (const link of root.querySelectorAll("a.product"))
    assert.equal(link.getAttribute("href"), "#/new?purpose=working_capital");
  dom.window.close();
});
test("smart application waits for a server quote and sends purpose category", async () => {
  const { dom, w, root, calls } = setup({
    hash: "/new",
    overrides: {
      "/applications": (options) => ({
        ok: true,
        status: 200,
        json: async () =>
          options.method === "POST"
            ? { ...application, pricing: { annual_rate: "19.4" } }
            : [],
      }),
      "/applications/a1": application,
      "/applications/a1/history": [],
    },
  });
  await until(() => root.querySelector("[data-quote-ready=true]"));
  const form = root.querySelector("form");
  form.elements.purpose.value = "Закупка товаров";
  form.elements.purpose_category.value = "working_capital";
  form.elements.purpose_category.dispatchEvent(
    new w.Event("change", { bubbles: true }),
  );
  await until(() => form.dataset.quoteReady === "true");
  submit(w, form, form.querySelector("[value=draft]"));
  await until(() =>
    calls.some((c) => c.key === "/applications" && c.method === "POST"),
  );
  const payload = JSON.parse(
    calls.find((c) => c.key === "/applications" && c.method === "POST").body,
  );
  assert.equal(payload.purpose_category, "working_capital");
  assert.equal("product_id" in payload, false);
  dom.window.close();
});

test("editing a term does not create premature validation errors and clears old ones", async () => {
  const { dom, w, root } = setup({ hash: "/new" });
  await until(() => root.querySelector("[data-quote-ready=true]"));
  const term = root.querySelector("[name=term_months]");
  term.value = "";
  term.dispatchEvent(new w.Event("input", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 350));
  assert.equal(root.querySelector("[data-error]").textContent, "");
  assert.equal(term.hasAttribute("aria-invalid"), false);
  term.dispatchEvent(new w.Event("invalid", { cancelable: true }));
  assert.equal(term.getAttribute("aria-invalid"), "true");
  term.value = "21";
  term.dispatchEvent(new w.Event("input", { bubbles: true }));
  assert.equal(term.hasAttribute("aria-invalid"), false);
  assert.equal(root.querySelector("[data-error]").textContent, "");
  await until(() => root.querySelector("[data-quote-ready=true]"));
  dom.window.close();
});
test("unconfigured registry explains the source without sending a failing refresh", async () => {
  const { dom, root, calls } = setup({
    hash: "/company",
    overrides: {
      "/company/registry-status": { configured: false, provider: null },
    },
  });
  await until(() => root.querySelector("[data-action=refresh-company]"));
  root.querySelector("[data-action=refresh-company]").click();
  assert.equal(root.querySelector(".registry-info").hidden, false);
  assert.match(root.querySelector(".registry-info").textContent, /ЕГРЮЛ/);
  assert.match(
    root.querySelector(".registry-info").textContent,
    /Сейчас источник не подключён/,
  );
  assert.equal(
    calls.some((c) => c.key === "/company/refresh"),
    false,
  );
  dom.window.close();
});

test('applications combine search and status filters and sort amounts', async () => {
  const {dom,w,root} = setup({ hash:'/applications', overrides:{'/applications':[
    {...application,id:'first',purpose:'Оборудование',status:'DECISION',requested_amount:'100000'},
    {...application,id:'second',purpose:'Товары',status:'REJECTED',requested_amount:'900000'}
  ]}});
  await until(() => root.querySelector('[data-application-search]'));
  const search = root.querySelector('[data-application-search]');
  search.value='оборудование'; search.dispatchEvent(new w.Event('input',{bubbles:true}));
  assert.equal(root.querySelectorAll('tbody tr').length,1);
  assert.match(root.querySelector('tbody').textContent,/first/);
  const status=root.querySelector('[data-application-status]'); status.value='REJECTED'; status.dispatchEvent(new w.Event('change',{bubbles:true}));
  assert.match(root.querySelector('.empty').textContent,/Ничего не найдено/);
  root.querySelector('[data-application-search]').value='';
  root.querySelector('[data-application-search]').dispatchEvent(new w.Event('input',{bubbles:true}));
  assert.match(root.querySelector('tbody').textContent,/second/);
  const all=root.querySelector('[data-application-status]'); all.value='';all.dispatchEvent(new w.Event('change',{bubbles:true}));
  const sort=root.querySelector('[data-application-sort]');sort.value='amount';sort.dispatchEvent(new w.Event('change',{bubbles:true}));
  assert.match(root.querySelector('tbody tr').textContent,/second/);
  dom.window.close();
});
test('account modal is the only visible logout entry and closes the session', async () => {
  const {dom,w,root} = setup();
  await until(() => root.querySelector('[data-action=account]'));
  assert.equal(root.querySelector('[data-action=logout]'),null);
  root.querySelector('[data-action=account]').click();
  const dialog=w.document.querySelector('dialog');
  assert.match(dialog.textContent,/Иван Иванов/);
  assert.match(dialog.textContent,/ООО «Проверка»/);
  dialog.querySelector('[data-dialog-logout]').click();
  await until(() => root.querySelector('[data-form=login]'));
  assert.equal(w.sessionStorage.getItem('credit-token'),null);
  dom.window.close();
});
test('notifications use real events and remember read state per account', async () => {
  const {dom,w,root} = setup({overrides:{'/applications':[application],'/applications/a1/history':[
    {id:'event-approved',to_status:'DECISION',from_status:'SCORING',occurred_at:'2026-10-24T13:00:00Z'}
  ]}});
  await until(() => root.querySelector('[data-unread]')?.textContent === '1');
  root.querySelector('[data-action=notifications]').click();
  await until(() => w.document.querySelector('[data-read-all]'));
  assert.match(w.document.querySelector('dialog').textContent,/Предварительно одобрено/);
  w.document.querySelector('[data-read-all]').click();
  assert.equal(root.querySelector('[data-unread]').hidden,true);
  assert.deepEqual(JSON.parse(w.localStorage.getItem('credit-read-u1')),['event-approved']);
  dom.window.close();
});
test('document export downloads company data without authentication secrets', async () => {
  const {dom,w,root}=setup({hash:'/documents'});
  let exported;
  w.URL.createObjectURL=blob => {exported=blob;return 'blob:test';};
  w.URL.revokeObjectURL=()=>{};
  w.HTMLAnchorElement.prototype.click=function(){ assert.match(this.download,/credit-company/); };
  await until(() => root.querySelector('[data-export=company]'));
  root.querySelector('[data-export=company]').click();
  await until(() => exported);
  const reader=new w.FileReader();
  const text=await new Promise(resolve=>{reader.onload=()=>resolve(reader.result);reader.readAsText(exported);});
  const result=JSON.parse(text);
  assert.equal(result.data.inn,company.inn);
  assert.equal(text.includes('test-token'),false);
  dom.window.close();
});

test('modal locks background and scrolling, then restores both on close', async () => {
  const {dom,w,root}=setup();
  await until(()=>root.querySelector('[data-action=account]'));
  w.document.documentElement.style.overflow='auto';
  root.querySelector('[data-action=account]').click();
  assert.equal(root.inert,true);
  assert.equal(w.document.documentElement.style.overflow,'hidden');
  assert.equal(w.document.body.style.overflow,'hidden');
  w.document.querySelector('.dialog-close').click();
  assert.equal(Boolean(root.inert),false);
  assert.equal(w.document.documentElement.style.overflow,'auto');
  assert.equal(w.document.body.style.overflow,'');
  dom.window.close();
});
test('applications show local time and sort ascending amounts and terms', async () => {
  const {dom,w,root}=setup({hash:'/applications',overrides:{'/applications':[
    {...application,id:'larger',requested_amount:'900000',term_months:6},
    {...application,id:'smaller',requested_amount:'100000',term_months:24}
  ]}});
  await until(()=>root.querySelector('[data-application-sort]'));
  assert.match(root.querySelector('.application-time').textContent,/\d{2}:\d{2}/);
  const choose=value=>{const el=root.querySelector('[data-application-sort]');el.value=value;el.dispatchEvent(new w.Event('change',{bubbles:true}));};
  choose('amount-asc');assert.match(root.querySelector('tbody tr').textContent,/smaller/);
  choose('term-asc');assert.match(root.querySelector('tbody tr').textContent,/larger/);
  choose('term-desc');assert.match(root.querySelector('tbody tr').textContent,/smaller/);
  dom.window.close();
});


test("product purpose prefills the shared form and other remains last", async () => {
  for (const category of ["investment", "working_capital", "urgent"]) {
    const {dom,root,w} = setup({hash:"/new?purpose="+category});
    await until(()=>root.querySelector("[name=purpose_category]"));
    const select=root.querySelector("[name=purpose_category]");
    assert.equal(select.value,category);
    assert.equal(select.options[select.options.length-1].value,"other");
    select.value="other";select.dispatchEvent(new w.Event("change",{bubbles:true}));
    assert.equal(select.value,"other");
    dom.window.close();
  }
});

test('unknown financial and credit fields remain blank and are not saved as zeros', async () => {
  const {dom,w,root,calls}=setup({hash:'/company/financials',overrides:{
    '/company/financials':{revenue_annual:null,profit_annual:null,expenses_annual:null,employees:null,current_debt:null,source:'DADATA',field_sources:{}},
    '/company/credit-history':{active_credits:null,closed_credits:null,overdue_count:null,overdue_amount:null,source:'UNAVAILABLE'}
  }});
  await until(()=>root.querySelector('[data-form=financials]'));
  const form=root.querySelector('[data-form=financials]');
  assert.equal(form.elements.revenue_annual.value,'');
  root.querySelector('[data-action=edit-financials]').click();
  form.elements.current_debt.value='0';
  submit(w,form);
  await until(()=>calls.some(c=>c.method==='PATCH'));
  const patch=JSON.parse(calls.find(c=>c.method==='PATCH').body);
  assert.deepEqual(patch,{current_debt:0});
  assert.equal(root.querySelector('[name=active_credits]').value,'');
  dom.window.close();
});

test('document preview is editable and saves only after explicit confirmation', async () => {
  const {dom,w,root,calls}=setup({hash:'/documents',overrides:{
    '/company/documents/preview?filename=report.txt':{id:'doc1',filename:'report.txt',values:{revenue_annual:'1250000'},evidence:{revenue_annual:'Выручка 1250000'},report_year:2025,inn:null,unit:'rub',method:'TEXT + QWEN',warnings:[],text_excerpt:'Выручка 1250000 руб.',company_mismatch:false},
    '/company/documents/doc1/confirm':{saved:true},
  }});
  await until(()=>root.querySelector('[data-document-file]'));
  const input=root.querySelector('[data-document-file]');
  Object.defineProperty(input,'files',{value:[new w.File(['Выручка 1250000 руб.'],'report.txt',{type:'text/plain'})]});
  input.dispatchEvent(new w.Event('change',{bubbles:true}));
  await until(()=>w.document.querySelector('[data-import-confirm]'));
  assert.equal(calls.some(c=>c.key.endsWith('/confirm')),false);
  const form=w.document.querySelector('[data-import-confirm]');
  assert.equal(form.elements.revenue_annual.value,'1250000');
  assert.equal(form.elements.current_debt.value,'');
  form.elements.revenue_annual.value='1500000';
  form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
  assert.equal(calls.some(c=>c.key.endsWith('/confirm')),false);
  form.elements.accepted.checked=true;
  form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
  await until(()=>calls.some(c=>c.key.endsWith('/confirm')));
  const payload=JSON.parse(calls.find(c=>c.key.endsWith('/confirm')).body);
  assert.deepEqual(payload,{accepted:true,financials:{report_year:2025,revenue_annual:1500000}});
  dom.window.close();
});

test('phone navigation preserves all destinations and account access', async () => {
  const {dom,w,root}=setup();
  try {
    await until(()=>root.querySelector('.nav'));
    const links=[...root.querySelectorAll('.nav a')];
    assert.equal(links.length,5);
    assert.deepEqual(links.map(a=>a.dataset.mobileLabel),['Главная','Кредиты','Заявки','Компания','Документы']);
    assert.ok(links.every(a=>a.getAttribute('aria-label') && a.querySelector('svg')));
    root.querySelector('[data-action=account]').click();
    assert.ok(w.document.querySelector('dialog [data-dialog-logout]'));
  } finally {dom.window.close();}
});

test('application cards retain field labels and the application destination', async () => {
  const {dom,root}=setup({hash:'/applications',overrides:{'/applications':[application]}});
  try {
    await until(()=>root.querySelector('.application-table tbody tr'));
    const cells=[...root.querySelectorAll('.application-table tbody tr td')];
    assert.deepEqual(cells.map(td=>td.dataset.label),['Продукт / заявка','Сумма','Срок','Предварительная ставка','Статус','Дата','Действие']);
    assert.equal(cells[6].querySelector('a').getAttribute('href'),'#/applications/a1');
    assert.equal(root.querySelectorAll('th[scope=col]').length,7);
  } finally {dom.window.close();}
});

test('numeric keyboards and visible viewport follow mobile input needs', async () => {
  const {dom,w,root}=setup({hash:'/new',viewport:{height:720,offsetTop:0}});
  try {
    await until(()=>root.querySelector('[name=term_months]'));
    assert.equal(root.querySelector('[name=term_months]').inputMode,'numeric');
    assert.equal(root.querySelector('[name=requested_amount]').inputMode,'decimal');
    assert.equal(w.document.documentElement.style.getPropertyValue('--visible-height'),'720px');
    w.visualViewport.height=350;
    w.visualViewport.offsetTop=120;
    w.visualViewport.dispatchEvent(new w.Event('resize'));
    assert.equal(w.document.documentElement.style.getPropertyValue('--visible-height'),'350px');
    assert.equal(w.document.documentElement.style.getPropertyValue('--visual-top'),'120px');
  } finally {dom.window.close();}
});

test('ordinary account cannot enter staff console or request staff data', async()=>{
  const {dom,root,calls}=setup({hash:'/admin'});
  try{
    await until(()=>root.textContent.includes('Доступ ограничен'));
    assert.equal(root.querySelector('.nav a[href="#/admin"]'),null);
    assert.equal(calls.some(c=>c.key.startsWith('/admin/')),false);
  }finally{dom.window.close();}
});

test('administrator overview opens staff navigation and queue filters',async()=>{
  const {dom,root}=setup({hash:'/admin',overrides:{
    '/auth/me':{...user,role:'ADMIN'},
    '/admin/overview':{users:12,companies:7,applications:18,blocked_users:1,statuses:{MANUAL_REVIEW:3}}
  }});
  try{
    await until(()=>root.querySelector('.admin-status-grid'));
    assert.ok(root.querySelector('.nav a[href="#/admin"]'));
    assert.equal(root.querySelectorAll('.admin-metrics .card').length,4);
    assert.match(root.querySelector('[href="#/admin?section=applications&status=MANUAL_REVIEW"]').textContent,/3/);
    assert.equal(root.querySelectorAll('.admin-tabs a').length,4);
  }finally{dom.window.close();}
});

test('reviewer sees queue only and customer text is escaped',async()=>{
  const {dom,root,calls}=setup({hash:'/admin',overrides:{
    '/auth/me':{...user,role:'REVIEWER'},
    '/admin/applications?offset=0&limit=25':{items:[{...application,company_name:'<img src=x onerror=alert(1)>',inn:'7701234567',owner_email:'owner@example.com'}],total:1,offset:0,limit:25}
  }});
  try{
    await until(()=>root.querySelector('.admin-application'));
    assert.equal(root.querySelectorAll('.admin-tabs a').length,1);
    assert.equal(root.querySelector('.admin-application img'),null);
    assert.match(root.querySelector('.admin-application').textContent,/<img/);
    assert.equal(root.querySelector('.admin-application').getAttribute('href'),'#/admin/a1');
    assert.equal(calls.some(c=>c.key.startsWith('/admin/users')||c.key==='/admin/overview'),false);
  }finally{dom.window.close();}
});

test('user access change sends role and blocking only with a recorded reason',async()=>{
  const changed={...user,id:'client1',email:'client@example.com',role:'USER',is_active:true,company_name:'Компания'};
  const {dom,w,root,calls}=setup({hash:'/admin?section=users',overrides:{
    '/auth/me':{...user,role:'ADMIN'},
    '/admin/users?offset=0&limit=25':{items:[changed],total:1,offset:0,limit:25},
    '/admin/users/client1':changed
  }});
  try{
    await until(()=>root.querySelector('[data-admin-user]'));
    assert.equal(calls.some(c=>c.method==='PATCH'),false);
    root.querySelector('[data-admin-user]').click();
    const dialog=w.document.querySelector('dialog'),form=dialog.querySelector('form');
    form.elements.role.value='REVIEWER';form.elements.active.value='false';form.elements.reason.value='Проверка доступа';
    form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
    await until(()=>calls.some(c=>c.method==='PATCH'));
    assert.deepEqual(JSON.parse(calls.find(c=>c.method==='PATCH').body),{role:'REVIEWER',is_active:false,reason:'Проверка доступа'});
  }finally{dom.window.close();}
});

test('staff review requires a second explicit confirmation and keeps original assessment visible',async()=>{
  const decision={outcome:'CONDITIONAL_APPROVAL',source:'AI',risk_score:45,explanation:'Проверить источник',conditions:['Документы'],top_factors:[]};
  const {dom,w,root,calls}=setup({hash:'/admin/a1',overrides:{
    '/auth/me':{...user,role:'ADMIN'},
    '/admin/applications/a1':{application:{...application,status:'MANUAL_REVIEW'},company,owner:{full_name:'Иван',email:'owner@example.com'},decision,review:null,events:[],snapshots:[{version:1,captured_at:application.created_at,data:{source:'USER_INPUT'}}]},
    '/admin/applications/a1/review':{status:'REJECTED'}
  }});
  try{
    await until(()=>root.querySelector('[data-admin-review]'));
    assert.match(root.textContent,/Первоначальная оценка/);
    assert.match(root.querySelector('.admin-snapshots').textContent,/USER_INPUT/);
    const form=root.querySelector('[data-admin-review]');form.elements.outcome.value='REJECTED';form.elements.comment.value='Источники не подтверждены';
    form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
    assert.equal(calls.some(c=>c.key.endsWith('/review')),false);
    w.document.querySelector('[data-admin-confirm]').click();
    await until(()=>calls.some(c=>c.key.endsWith('/review')));
    assert.deepEqual(JSON.parse(calls.find(c=>c.key.endsWith('/review')).body),{outcome:'REJECTED',comment:'Источники не подтверждены'});
  }finally{dom.window.close();}
});

test('login accepts an administrator alias while registration still requests email',async()=>{
  for(const register of [false,true]){
    const {dom,root}=setup({hash:register?'/register':'/login',token:false});
    try{
      const field=root.querySelector('input[name=email]');
      assert.equal(field.type,register?'email':'text');
      assert.equal(field.autocomplete,register?'email':'username');
      assert.equal(field.getAttribute('autocapitalize'),'none');
    }finally{dom.window.close();}
  }
});
