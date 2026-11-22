import { Navigate, Route, Routes } from 'react-router-dom';

import { useSession } from '@/features/session/SessionContext';
import { can } from '@/routes/permissions';

import AnimalFormPage from './AnimalFormPage';
import ProfilePage from './ProfilePage';
import RegisterPage from './RegisterPage';
import SetupPage from './SetupPage';

export default function LivestockRoutes() {
  const { role } = useSession();
  return (
    <Routes>
      <Route index element={<RegisterPage />} />
      {can(role, 'livestock', 'create') && <Route path="new" element={<AnimalFormPage />} />}
      {can(role, 'livestock', 'manage') && <Route path="setup" element={<SetupPage />} />}
      <Route path=":id" element={<ProfilePage />} />
      {can(role, 'livestock', 'update') && <Route path=":id/edit" element={<AnimalFormPage />} />}
      <Route path="*" element={<Navigate to="/livestock" replace />} />
    </Routes>
  );
}
