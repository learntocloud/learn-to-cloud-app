import { SignUp } from '@clerk/clerk-react';
import { useEffect } from 'react';
import { clerkAppearance } from '../shared/clerkAppearance';

export function SignUpPage() {
  useEffect(() => {
    document.title = 'Sign Up | Learn to Cloud';
  }, []);

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
