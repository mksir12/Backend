function renderPreview() {
  const html = document.getElementById("htmlInput").value;
  const encoded = encodeURIComponent(btoa(html)); // base64 + URI encoding
  window.location.href = `/viewer.html?code=${encoded}`;
}
