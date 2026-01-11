import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'standalone', // Required for Container Apps deployment
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "img.clerk.com",
      },
    ],
  },
};

export default nextConfig;
