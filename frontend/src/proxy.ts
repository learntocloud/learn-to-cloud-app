/**
 * Clerk Authentication Middleware
 * 
 * Named "proxy.ts" per Next.js 16 convention (formerly middleware.ts).
 * This is NOT an HTTP proxy - it intercepts requests to protect private routes.
 */
import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'

const isPublicRoute = createRouteMatcher([
  '/',
  '/sign-in(.*)',
  '/sign-up(.*)',
  '/phases(.*)',    // Allow viewing phases without auth
  '/phase[0-9](.*)', // Allow viewing phase/topic pages without auth (phase0, phase1, etc.)
  '/api/(.*)',       // API routes are proxied to backend which handles its own auth
])

export default clerkMiddleware(async (auth, request) => {
  if (!isPublicRoute(request)) {
    await auth.protect()
  }
})

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
  ],
}
