(() => {
  "use strict";

  const STORAGE_KEY = "dailyaiwire.todo.v1";

  const els = {
    form: document.getElementById("new-form"),
    input: document.getElementById("new-input"),
    list: document.getElementById("list"),
    counter: document.getElementById("counter"),
    empty: document.getElementById("empty"),
    clear: document.getElementById("clear-completed"),
    filters: document.querySelectorAll(".filter"),
  };

  let todos = load();
  let filter = "all";

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function save() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(todos));
  }

  function add(text) {
    const trimmed = text.trim();
    if (!trimmed) return;
    todos.unshift({
      id: crypto.randomUUID(),
      text: trimmed,
      done: false,
      created: Date.now(),
    });
    save();
    render();
  }

  function toggle(id) {
    const t = todos.find((x) => x.id === id);
    if (!t) return;
    t.done = !t.done;
    save();
    render();
  }

  function remove(id) {
    todos = todos.filter((x) => x.id !== id);
    save();
    render();
  }

  function clearCompleted() {
    todos = todos.filter((x) => !x.done);
    save();
    render();
  }

  function visible() {
    if (filter === "active") return todos.filter((t) => !t.done);
    if (filter === "completed") return todos.filter((t) => t.done);
    return todos;
  }

  function render() {
    const items = visible();
    els.list.replaceChildren(...items.map(renderItem));

    const remaining = todos.filter((t) => !t.done).length;
    const total = todos.length;
    els.counter.textContent =
      total === 0
        ? "No tasks yet"
        : `${remaining} of ${total} remaining`;

    els.empty.hidden = items.length > 0;
    els.clear.hidden = !todos.some((t) => t.done);
  }

  function renderItem(todo) {
    const li = document.createElement("li");
    li.className = "item" + (todo.done ? " done" : "");
    li.dataset.id = todo.id;

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "checkbox";
    checkbox.checked = todo.done;
    checkbox.setAttribute("aria-label", "Mark complete");
    checkbox.addEventListener("change", () => toggle(todo.id));

    const text = document.createElement("span");
    text.className = "text";
    text.textContent = todo.text;

    const del = document.createElement("button");
    del.type = "button";
    del.className = "delete-btn";
    del.setAttribute("aria-label", "Delete task");
    del.textContent = "×";
    del.addEventListener("click", () => remove(todo.id));

    li.append(checkbox, text, del);
    return li;
  }

  els.form.addEventListener("submit", (e) => {
    e.preventDefault();
    add(els.input.value);
    els.input.value = "";
    els.input.focus();
  });

  els.clear.addEventListener("click", clearCompleted);

  els.filters.forEach((btn) => {
    btn.addEventListener("click", () => {
      filter = btn.dataset.filter;
      els.filters.forEach((b) => {
        const active = b === btn;
        b.classList.toggle("is-active", active);
        b.setAttribute("aria-selected", String(active));
      });
      render();
    });
  });

  render();
})();
