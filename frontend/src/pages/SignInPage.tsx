import { SignIn } from '@clerk/clerk-react';
import { useEffect } from 'react';
import { clerkAppearance } from '../shared/clerkAppearance';

export function SignInPage() {
  useEffect(() => {
    document.title = 'Sign In | Learn to Cloud';
  }, []);

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
