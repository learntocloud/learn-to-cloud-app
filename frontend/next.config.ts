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
  // Compression is handled by Azure, but good for local dev
  compress: true,
  // Generate ETags for static assets
  generateEtags: true,
  // Production optimizations
  poweredByHeader: false, // Remove X-Powered-By header (security + tiny perf)
  // Cache static pages aggressively
  headers: async () => [
    {
      source: '/content/:path*',
      headers: [
        { key: 'Cache-Control', value: 'public, max-age=3600, stale-while-revalidate=86400' },
      ],
    },
  ],
};

export default nextConfig;
