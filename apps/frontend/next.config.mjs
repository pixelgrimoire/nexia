/** @type {import('next').NextConfig} */
const API_GATEWAY_URL = process.env.API_GATEWAY_URL || 'http://api-gateway:8000';
const ANALYTICS_URL = process.env.ANALYTICS_URL || 'http://analytics:8000';

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      // Route analytics first so it doesn't get captured by the generic /api rule
      {
        source: '/api/analytics/:path*',
        destination: `${ANALYTICS_URL}/api/analytics/:path*`,
      },
      {
        source: '/api/:path*',
        destination: `${API_GATEWAY_URL}/api/:path*`,
      },
      {
        source: '/metrics',
        destination: `${API_GATEWAY_URL}/metrics`,
      },
      {
        source: '/internal/:path*',
        destination: `${API_GATEWAY_URL}/internal/:path*`,
      },
    ];
  },
};

export default nextConfig;
