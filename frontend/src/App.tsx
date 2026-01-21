import { Routes, Route } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { SignedIn, SignedOut, RedirectToSignIn } from '@clerk/clerk-react';
import { Layout } from './components/Layout';

const HomePage = lazy(() => import('./pages/HomePage').then(m => ({ default: m.HomePage })));
const DashboardPage = lazy(() => import('./pages/DashboardPage').then(m => ({ default: m.DashboardPage })));
const PhasesPage = lazy(() => import('./pages/PhasesPage').then(m => ({ default: m.PhasesPage })));
const PhasePage = lazy(() => import('./pages/PhasePage').then(m => ({ default: m.PhasePage })));
const TopicPage = lazy(() => import('./pages/TopicPage').then(m => ({ default: m.TopicPage })));
const FAQPage = lazy(() => import('./pages/FAQPage').then(m => ({ default: m.FAQPage })));
const UpdatesPage = lazy(() => import('./pages/UpdatesPage').then(m => ({ default: m.UpdatesPage })));
const CertificatesPage = lazy(() => import('./pages/CertificatesPage').then(m => ({ default: m.CertificatesPage })));
const ProfilePage = lazy(() => import('./pages/ProfilePage').then(m => ({ default: m.ProfilePage })));
const VerifyPage = lazy(() => import('./pages/VerifyPage').then(m => ({ default: m.VerifyPage })));
const SignInPage = lazy(() => import('./pages/SignInPage').then(m => ({ default: m.SignInPage })));
const SignUpPage = lazy(() => import('./pages/SignUpPage').then(m => ({ default: m.SignUpPage })));
const ProfileRedirect = lazy(() => import('./pages/ProfileRedirect').then(m => ({ default: m.ProfileRedirect })));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage').then(m => ({ default: m.NotFoundPage })));

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SignedIn>{children}</SignedIn>
      <SignedOut>
        <RedirectToSignIn />
      </SignedOut>
    </>
  );
}

function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
    </div>
  );
}

export function App() {
  return (
    <Layout>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/phases" element={<PhasesPage />} />
          <Route path="/faq" element={<FAQPage />} />
          <Route path="/updates" element={<UpdatesPage />} />
          <Route path="/sign-in/*" element={<SignInPage />} />
          <Route path="/sign-up/*" element={<SignUpPage />} />
          <Route path="/user/:username" element={<ProfilePage />} />
          <Route path="/verify" element={<VerifyPage />} />
          <Route path="/verify/:code" element={<VerifyPage />} />

          {/* Protected routes must come before dynamic /:phaseSlug to avoid collision */}
          <Route
            path="/profile"
            element={
              <ProtectedRoute>
                <ProfileRedirect />
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <DashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/certificates"
            element={
              <ProtectedRoute>
                <CertificatesPage />
              </ProtectedRoute>
            }
          />

          {/* Dynamic phase routes - placed after static routes */}
          <Route path="/:phaseSlug" element={<PhasePage />} />
          <Route path="/:phaseSlug/:topicSlug" element={<TopicPage />} />

          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}
