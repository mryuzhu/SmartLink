function showToast(message, category = "info") {
  const stack = document.getElementById("toast-stack");
  if (!stack) return;
  const toast = document.createElement("div");
  toast.className = `toast toast-${category}`;
  toast.textContent = message;
  stack.appendChild(toast);
  window.setTimeout(() => {
    toast.remove();
  }, 3600);
}

function toggleTokenVisibility(inputId, labelId) {
  const input = document.getElementById(inputId);
  const label = document.getElementById(labelId);
  if (!input || !label) return;
  const nextType = input.type === "password" ? "text" : "password";
  input.type = nextType;
  label.textContent = nextType === "text" ? "隐藏" : "显示";
}

function applyLoadingState(button, isLoading) {
  if (!(button instanceof HTMLElement)) return;
  if (isLoading) {
    if (!button.dataset.originalText) {
      button.dataset.originalText = button.textContent.trim();
    }
    button.textContent = button.dataset.loadingText || "处理中...";
    button.disabled = true;
    button.classList.add("is-loading");
    return;
  }
  if (button.dataset.originalText) {
    button.textContent = button.dataset.originalText;
  }
  button.disabled = false;
  button.classList.remove("is-loading");
}

function fillHiddenTargets(formId, values) {
  const form = document.getElementById(formId);
  if (!form) return;
  form.querySelectorAll("input[name='selected_names']").forEach((node) => node.remove());
  values.forEach((value) => {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "selected_names";
    input.value = value;
    form.appendChild(input);
  });
}

function selectedActionNames() {
  return [...document.querySelectorAll(".action-selector:checked")].map((item) => item.value);
}

function openActionModal(mode, actionName) {
  const shell = document.getElementById("action-modal-shell");
  if (!shell) return;
  const title = document.getElementById("action-modal-title");
  const form = document.getElementById("action-form");
  const actionDataNode = document.getElementById("action-data");
  const actionMap = actionDataNode ? JSON.parse(actionDataNode.textContent) : {};
  form.reset();
  document.getElementById("enabled").checked = true;
  document.getElementById("allow_api").checked = true;
  document.getElementById("old_name").value = "";
  title.textContent = "新建动作";
  if (mode === "edit" && actionName && actionMap[actionName]) {
    const action = actionMap[actionName];
    title.textContent = `编辑动作: ${actionName}`;
    document.getElementById("old_name").value = actionName;
    document.getElementById("name").value = actionName;
    document.getElementById("type").value = action.type === "music" ? "exe" : action.type || "exe";
    document.getElementById("category").value = action.category || "默认";
    document.getElementById("tags").value = (action.tags || []).join(", ");
    document.getElementById("uri_scheme").value = action.uri_scheme || "";
    document.getElementById("bafy_topic").value = action.bafy_topic || "";
    document.getElementById("card_ids").value = (action.card_ids || []).join(", ");
    document.getElementById("description").value = action.description || "";
    document.getElementById("cmd").value = action.cmd || "";
    document.getElementById("favorite").checked = Boolean(action.favorite);
    document.getElementById("allow_api").checked = Boolean(action.allow_api);
    document.getElementById("enabled").checked = Boolean(action.enabled);
  }
  shell.hidden = false;
  document.body.style.overflow = "hidden";
}

function closeActionModal() {
  const shell = document.getElementById("action-modal-shell");
  if (!shell) return;
  shell.hidden = true;
  document.body.style.overflow = "";
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".toast").forEach((toast) => {
    window.setTimeout(() => toast.remove(), 3200);
  });

  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const submitter = event.submitter;
      applyLoadingState(submitter, true);
    });
  });

  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = document.getElementById(button.dataset.copyTarget);
      if (!target) return;
      applyLoadingState(button, true);
      try {
        await navigator.clipboard.writeText(target.textContent.trim());
        showToast("已复制到剪贴板。", "success");
      } catch {
        showToast("复制失败，请手动复制。", "error");
      } finally {
        applyLoadingState(button, false);
      }
    });
  });

  document.querySelectorAll("[data-open-action-modal]").forEach((button) => {
    button.addEventListener("click", () => {
      openActionModal(button.dataset.openActionModal, button.dataset.actionName);
    });
  });

  document.querySelectorAll("[data-close-action-modal]").forEach((button) => {
    button.addEventListener("click", closeActionModal);
  });

  document.getElementById("adb-pair-toggle")?.addEventListener("click", () => {
    const pairForm = document.getElementById("adb-pair-form");
    if (!pairForm) return;
    pairForm.hidden = !pairForm.hidden;
  });

  document.getElementById("select-all-actions")?.addEventListener("change", (event) => {
    document.querySelectorAll(".action-selector").forEach((checkbox) => {
      checkbox.checked = event.target.checked;
    });
  });

  document.getElementById("show-action-details")?.addEventListener("change", (event) => {
    document.body.classList.toggle("show-action-details", event.target.checked);
  });

  document.getElementById("bulk-delete-button")?.addEventListener("click", () => {
    const selected = selectedActionNames();
    if (!selected.length) {
      showToast("请至少选择一个动作。", "warning");
      return;
    }
    if (!window.confirm(`确认删除 ${selected.length} 个动作吗？`)) {
      return;
    }
    applyLoadingState(document.getElementById("bulk-delete-button"), true);
    fillHiddenTargets("bulk-delete-form", selected);
    document.getElementById("bulk-delete-form").submit();
  });

  document.getElementById("bulk-export-button")?.addEventListener("click", () => {
    const selected = selectedActionNames();
    if (!selected.length) {
      showToast("请至少选择一个动作。", "warning");
      return;
    }
    applyLoadingState(document.getElementById("bulk-export-button"), true);
    fillHiddenTargets("bulk-export-form", selected);
    document.getElementById("bulk-export-form").submit();
  });

  const brightnessSlider = document.getElementById("mobile-brightness");
  const brightnessValue = document.getElementById("mobile-brightness-value");
  if (brightnessSlider && brightnessValue) {
    brightnessSlider.addEventListener("input", () => {
      brightnessValue.textContent = brightnessSlider.value;
    });
  }

  function mobileToken() {
    return document.getElementById("mobile-token-input")?.value?.trim() || "";
  }

  async function postMobile(path, payload = {}, button = null) {
    const apiBase = document.getElementById("mobile-api-base")?.dataset.apiBase;
    const token = mobileToken();
    if (!apiBase || !token) {
      showToast("请先输入完整 Token。", "warning");
      return;
    }
    applyLoadingState(button, true);
    try {
      const response = await fetch(`${apiBase}${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-SmartLink-Token": token,
        },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      showToast(result.message || "请求已发送。", result.success ? "success" : "error");
    } catch {
      showToast("请求失败，请检查局域网连接。", "error");
    } finally {
      applyLoadingState(button, false);
    }
  }

  document.querySelectorAll("[data-mobile-action]").forEach((button) => {
    button.addEventListener("click", () => {
      postMobile(`/run/${encodeURIComponent(button.dataset.mobileAction)}`, {}, button);
    });
  });

  document.querySelectorAll("[data-mobile-system]").forEach((button) => {
    button.addEventListener("click", () => {
      postMobile(`/system/${button.dataset.mobileSystem}`, {}, button);
    });
  });

  document.getElementById("mobile-brightness-button")?.addEventListener("click", (event) => {
    postMobile(
      "/system/brightness",
      {
        value: Number(document.getElementById("mobile-brightness")?.value || 50),
      },
      event.currentTarget
    );
  });
});
