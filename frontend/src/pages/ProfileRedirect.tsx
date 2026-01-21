import { Navigate } from 'react-router-dom';
import { useUserInfo } from '@/lib/hooks';

export function ProfileRedirect() {
  const { data: userInfo, isLoading } = useUserInfo();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (userInfo?.github_username) {
    return <Navigate to={`/user/${userInfo.github_username}`} replace />;
  }

  // Fallback to dashboard if no username
  return <Navigate to="/dashboard" replace />;
}
