import type { NextConfig } from "next";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Only proxy API calls in development (localhost)
// In production, the frontend calls the API directly via NEXT_PUBLIC_API_URL
const isDevelopment = API_URL.includes('localhost') || API_URL.includes('127.0.0.1');

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
  
  // === COLD START OPTIMIZATIONS ===
  // Experimental features for faster startup
  experimental: {
    // Optimize package imports to reduce cold start time
    optimizePackageImports: [
      '@clerk/nextjs',
      '@microsoft/applicationinsights-web',
    ],
  },
  
  // Cache static pages aggressively
  headers: async () => [
    {
      source: '/content/:path*',
      headers: [
        { key: 'Cache-Control', value: 'public, max-age=3600, stale-while-revalidate=86400' },
      ],
    },
  ],
  // Proxy API calls to backend in development only
  // Required for dev containers/Codespaces where browser can't reach localhost:8000
  // In production, client-side JS calls the API URL directly (no proxy overhead)
  async rewrites() {
    if (!isDevelopment) {
      return [];
    }
    return [
      {
        source: '/api/:path*',
        destination: `${API_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
