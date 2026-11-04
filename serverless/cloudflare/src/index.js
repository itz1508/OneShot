// Isolated deployment boundary. The OneShot Python host remains authoritative.
// No task execution, receipt issuance, or unrestricted proxying occurs here.
export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return Response.json({ status: "ok", service: "oneshot-gateway" }, {
        headers: { "cache-control": "no-store" },
      });
    }
    return Response.json({ error: "not_found" }, { status: 404 });
  },
};
