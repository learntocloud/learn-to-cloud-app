import { Routes, Route } from 'react-router-dom';
import { SignedIn, SignedOut, RedirectToSignIn } from '@clerk/clerk-react';
import { Layout } from './components/Layout';
import { AppInsightsProvider } from './components/AppInsightsProvider';
import { CelebrationProvider } from './components/CelebrationProvider';

// Pages
import {
  HomePage,
  DashboardPage,
  PhasesPage,
  PhasePage,
  TopicPage,
  FAQPage,
  CertificatesPage,
  ProfilePage,
  VerifyPage,
  SignInPage,
  SignUpPage,
  NotFoundPage,
} from './pages';

// Protected route wrapper
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

export function App() {
  return (
    <AppInsightsProvider>
      <CelebrationProvider>
        <Layout>
          <Routes>
            {/* Public routes */}
            <Route path="/" element={<HomePage />} />
            <Route path="/phases" element={<PhasesPage />} />
            <Route path="/faq" element={<FAQPage />} />
            <Route path="/sign-in/*" element={<SignInPage />} />
            <Route path="/sign-up/*" element={<SignUpPage />} />
            <Route path="/user/:username" element={<ProfilePage />} />
            <Route path="/verify" element={<VerifyPage />} />
            <Route path="/verify/:code" element={<VerifyPage />} />

            {/* Phase and topic routes - show content but progress requires auth */}
            <Route path="/:phaseSlug" element={<PhasePage />} />
            <Route path="/:phaseSlug/:topicSlug" element={<TopicPage />} />

            {/* Protected routes */}
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

            {/* 404 */}
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Layout>
      </CelebrationProvider>
    </AppInsightsProvider>
  );
}
