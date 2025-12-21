import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Prompts from './pages/Prompts';
import Contacts from './pages/Contacts';
import ContactDetail from './pages/ContactDetail';
import UnknownLeads from './pages/UnknownLeads';
import UnknownLeadDetail from './pages/UnknownLeadDetail';
import Onboarding from './pages/Onboarding';
import Settings from './pages/Settings';
import SmsSettings from './pages/SmsSettings';
import ManageTenants from './pages/ManageTenants';
import PromptWizard from './pages/PromptWizard';
import './App.css';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/onboarding" element={
            <ProtectedRoute>
              <Onboarding />
            </ProtectedRoute>
          } />
          <Route
            path="/"
            element={
              <ProtectedRoute requireProfile>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="prompts" element={<Prompts />} />
            <Route path="prompts/wizard" element={<PromptWizard />} />
            <Route path="contacts" element={<Contacts />} />
            <Route path="contacts/:id" element={<ContactDetail />} />
            <Route path="unknown" element={<UnknownLeads />} />
            <Route path="unknown/:id" element={<UnknownLeadDetail />} />
            <Route path="settings" element={<Settings />} />
            <Route path="sms" element={<SmsSettings />} />
            <Route path="admin/tenants" element={<ManageTenants />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
