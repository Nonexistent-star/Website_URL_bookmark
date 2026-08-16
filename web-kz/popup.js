const BASE = "http://127.0.0.1:47811/wjkz";
const $ = id => document.getElementById(id);

async function init() {
  // 自动获取当前网页的名称与地址
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) {
      $("name").value = tab.title || "";
      $("url").value = tab.url || "";
    }
  } catch (e) { /* 权限不足时保持空，允许手填 */ }

  // 拉取主程序已有标签作为候选
  try {
    const r = await fetch(BASE + "/tags");
    const j = await r.json();
    $("tags").innerHTML = (j.tags || []).map(t =>
      `<option value="${t.replace(/"/g, "&quot;")}">`).join("");
  } catch (e) { /* 主程序未运行时忽略 */ }

  // 连通性检测
  try {
    await fetch(BASE + "/ping");
    $("msg").textContent = "";
  } catch (e) {
    $("msg").textContent = "未检测到 WebJump 主程序在运行，请先打开它。";
  }
}

$("save").onclick = async () => {
  const msg = $("msg");
  const url = $("url").value.trim();
  if (!url) { msg.textContent = "请填写网址。"; return; }
  $("save").disabled = true;
  msg.className = ""; msg.textContent = "正在添加…";
  try {
    const r = await fetch(BASE + "/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: $("name").value.trim(),
        url: url,
        tag: $("tag").value.trim(),
        open: $("open").value
      })
    });
    const j = await r.json();
    if (j && j.ok) {
      msg.className = "ok";
      msg.textContent = "已添加到 WebJump。";
      setTimeout(() => window.close(), 700);
    } else {
      msg.textContent = "添加失败：" + (j && j.msg || "未知错误");
    }
  } catch (e) {
    msg.textContent = "无法连接 WebJump 主程序，请确认它正在运行。";
  }
  $("save").disabled = false;
};

init();
