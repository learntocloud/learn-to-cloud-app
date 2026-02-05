import { SignIn } from '@clerk/clerk-react';
import { clerkAppearance } from '../shared/clerkAppearance';
import { useDocumentTitle } from '@/lib/useDocumentTitle';

export function SignInPage() {
  useDocumentTitle('Sign In | Learn to Cloud');

  return (
    <div className="min-h-screen flex items-center justify-center py-12">
      <SignIn
        appearance={clerkAppearance}
        routing="path"
        path="/sign-in"
        signUpUrl="/sign-up"
        fallbackRedirectUrl="/dashboard"
      />
    </div>
  );
}
