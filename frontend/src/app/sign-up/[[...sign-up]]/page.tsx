import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <div className="min-h-screen flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <SignUp 
        appearance={{
          elements: {
            rootBox: "mx-auto",
            card: "shadow-xl",
            socialButtonsBlockButton: "flex items-center justify-center gap-2",
            socialButtonsBlockButtonText: "font-medium",
            footer: "hidden",
            dividerRow: "hidden",
            form: "hidden",
          },
        }}
        routing="path"
        path="/sign-up"
      />
    </div>
  );
}
