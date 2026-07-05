// Reusable parameters modal, shared by the job-definitions and connections
// admin pages. Requires the markup from admin/_params_modal.html to be present.
// Call initParamsModal({...}) once (after the DOM is ready); it returns an
// object with open(owner), where owner = {id, name}.
//
//   collectionUrl(ownerId) -> URL for GET (list) and POST (create)
//   itemUrl(parameterId)   -> URL for PATCH (update) and DELETE
function initParamsModal({ collectionUrl, itemUrl }) {
  const dialog = document.getElementById("paramDialog");
  const form = document.getElementById("paramForm");
  const rows = document.getElementById("paramRows");
  const empty = document.getElementById("paramEmpty");
  const msg = document.getElementById("paramMsg");
  const formError = document.getElementById("paramFormError");
  const valueHint = document.getElementById("p-value-hint");
  const titleEl = document.getElementById("paramDialogTitle");
  let ownerId = null;
  let editId = null;
  let editHasValue = false;

  function showMsg(text, isError) {
    msg.textContent = text;
    msg.className = "form-msg " + (isError ? "error" : "ok");
  }

  function updateHint() {
    const secret = form.elements["is_secret"].checked;
    if (secret && editId && editHasValue) {
      valueHint.textContent = "Encrypted & masked. Leave blank to keep the current value.";
    } else if (secret) {
      valueHint.textContent = "Encrypted at rest and masked in the list.";
    } else {
      valueHint.textContent = "Stored as plain text and shown in the list.";
    }
  }

  function resetForm() {
    editId = null;
    editHasValue = false;
    form.reset();
    document.getElementById("paramFormTitle").textContent = "Add parameter";
    document.getElementById("paramSubmit").textContent = "Add parameter";
    document.getElementById("paramEditCancel").hidden = true;
    formError.textContent = "";
    updateHint();
  }

  function startEdit(p) {
    editId = p.id;
    editHasValue = p.has_value;
    form.elements["key"].value = p.key;
    form.elements["value_type"].value = p.value_type || "string";
    form.elements["is_secret"].checked = !!p.is_secret;
    form.elements["value"].value = p.is_secret ? "" : (p.value || "");
    document.getElementById("paramFormTitle").textContent = `Edit "${p.key}"`;
    document.getElementById("paramSubmit").textContent = "Save changes";
    document.getElementById("paramEditCancel").hidden = false;
    formError.textContent = "";
    updateHint();
    form.elements["key"].focus();
  }

  function render(list) {
    rows.innerHTML = "";
    empty.hidden = list.length > 0;
    list.forEach((p) => {
      const tr = document.createElement("tr");
      const keyTd = document.createElement("td");
      keyTd.textContent = p.key;
      if (p.is_secret) {
        const lock = document.createElement("i");
        lock.className = "bi bi-lock-fill param-lock";
        lock.title = "Secret (encrypted)";
        keyTd.appendChild(document.createTextNode(" "));
        keyTd.appendChild(lock);
      }
      const typeTd = document.createElement("td");
      typeTd.className = "param-type";
      typeTd.textContent = p.value_type || "string";
      const valTd = document.createElement("td");
      valTd.className = "param-value";
      if (p.is_secret) {
        valTd.textContent = p.has_value ? "••••••••" : "—";
      } else {
        const v = p.value == null ? "" : String(p.value);
        valTd.textContent = v === "" ? "—" : (v.length > 60 ? v.slice(0, 60) + "…" : v);
        if (v) valTd.title = v;
      }
      const actTd = document.createElement("td");
      actTd.className = "param-actions-col";
      const edit = document.createElement("button");
      edit.className = "btn-edit";
      edit.textContent = "Edit";
      edit.addEventListener("click", () => startEdit(p));
      const del = document.createElement("button");
      del.className = "btn-danger";
      del.textContent = "Delete";
      del.addEventListener("click", () => remove(p));
      actTd.appendChild(edit);
      actTd.appendChild(del);
      tr.appendChild(keyTd);
      tr.appendChild(typeTd);
      tr.appendChild(valTd);
      tr.appendChild(actTd);
      rows.appendChild(tr);
    });
  }

  function load() {
    fetch(collectionUrl(ownerId))
      .then((r) => r.json())
      .then((d) => render(d.parameters || []))
      .catch(() => showMsg("Failed to load parameters.", true));
  }

  function remove(p) {
    if (!confirm(`Delete parameter "${p.key}"? This cannot be undone.`)) return;
    fetch(itemUrl(p.id), { method: "DELETE" }).then((r) => {
      if (r.status === 204) {
        if (editId === p.id) resetForm();
        load();
        showMsg(`Deleted "${p.key}".`, false);
      } else {
        r.json().then((j) => showMsg(j.error || "Delete failed.", true));
      }
    });
  }

  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const key = form.elements["key"].value.trim();
    const value = form.elements["value"].value;
    const value_type = form.elements["value_type"].value;
    const is_secret = form.elements["is_secret"].checked;
    const editing = editId !== null;
    const url = editing ? itemUrl(editId) : collectionUrl(ownerId);
    const method = editing ? "PATCH" : "POST";
    fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value, value_type, is_secret }),
    })
      .then((r) => (r.ok ? r.json() : r.json().then((j) => Promise.reject(j.error || "Save failed."))))
      .then((saved) => {
        resetForm();
        load();
        showMsg(`${editing ? "Updated" : "Added"} "${saved.key}".`, false);
      })
      .catch((err) => { formError.textContent = err; });
  });

  document.getElementById("paramClose").addEventListener("click", () => dialog.close());
  document.getElementById("paramEditCancel").addEventListener("click", resetForm);
  document.getElementById("p-secret").addEventListener("change", updateHint);

  return {
    open(owner) {
      ownerId = owner.id;
      titleEl.textContent = `Parameters — ${owner.name}`;
      showMsg("", false);
      resetForm();
      render([]);
      load();
      dialog.showModal();
    },
  };
}
