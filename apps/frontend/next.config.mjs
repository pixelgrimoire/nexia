/** @type {import('next').NextConfig} */
const API_GATEWAY_URL = process.env.API_GATEWAY_URL || 'http://api-gateway:8000';

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
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
