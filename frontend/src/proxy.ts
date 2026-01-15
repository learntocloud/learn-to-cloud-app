/**
 * Clerk Authentication Middleware
 *
 * Protects private routes and allows public access to specified paths.
 * Authentication is handled by Clerk, with route-level privacy controlled at the API level.
 */
import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'

const isPublicRoute = createRouteMatcher([
  '/',
  '/sign-in(.*)',
  '/sign-up(.*)',
  '/phases(.*)',     // Allow viewing phases without auth
  '/phase[0-9](.*)', // Allow viewing phase/topic pages without auth (phase0, phase1, etc.)
  '/faq(.*)',        // FAQ page is public
  '/verify(.*)',     // Certificate verification pages must be public
  '/user/(.*)',      // Public user profile pages (privacy controlled at API level)
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
