import { SignUp } from '@clerk/clerk-react';
import { clerkAppearance } from '../shared/clerkAppearance';
import { useDocumentTitle } from '@/lib/useDocumentTitle';

export function SignUpPage() {
  useDocumentTitle('Sign Up | Learn to Cloud');

  return (
    <div className="min-h-screen flex items-center justify-center py-12">
      <SignUp
        appearance={clerkAppearance}
        routing="path"
        path="/sign-up"
        signInUrl="/sign-in"
        fallbackRedirectUrl="/dashboard"
      />
    </div>
  );
}
