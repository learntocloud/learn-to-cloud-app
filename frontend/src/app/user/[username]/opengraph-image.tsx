import { ImageResponse } from "next/og";

export const runtime = "edge";

export const alt = "Learn to Cloud Profile";
export const size = {
  width: 1200,
  height: 630,
};
export const contentType = "image/png";

// Note: We can't use the full getPublicProfile here in edge runtime
// due to Clerk auth limitations. Using a simplified OG image instead.

export default async function Image({ params }: { params: Promise<{ username: string }> }) {
  const { username } = await params;

  return new ImageResponse(
    (
      <div
        style={{
          height: "100%",
          width: "100%",
          display: "flex",
          flexDirection: "column",
          backgroundColor: "#0f172a",
          padding: "60px",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: "24px", marginBottom: "40px" }}>
          <div
            style={{
              width: 120,
              height: 120,
              borderRadius: "60px",
              background: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "white",
              fontSize: 48,
              fontWeight: "bold",
            }}
          >
            {username[0]?.toUpperCase() || "?"}
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ fontSize: 48, fontWeight: "bold", color: "white" }}>
              @{username}
            </div>
            <div style={{ fontSize: 24, color: "#94a3b8" }}>
              Learn to Cloud Journey
            </div>
          </div>
        </div>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Footer */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: "12px",
                background: "linear-gradient(135deg, #3b82f6, #06b6d4)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <span style={{ fontSize: 28 }}>☁️</span>
            </div>
            <span style={{ fontSize: 28, fontWeight: "bold", color: "white" }}>
              Learn to Cloud
            </span>
          </div>
          <div style={{ fontSize: 20, color: "#64748b" }}>learntocloud.guide</div>
        </div>
      </div>
    ),
    { ...size }
  );
}
