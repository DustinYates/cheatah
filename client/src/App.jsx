import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Prompts from './pages/Prompts';
import Contacts from './pages/Contacts';
import ContactDetail from './pages/ContactDetail';
import Calls from './pages/Calls';
import UnknownLeads from './pages/UnknownLeads';
import UnknownLeadDetail from './pages/UnknownLeadDetail';
import Plots from './pages/Plots';
import Onboarding from './pages/Onboarding';
import BusinessProfile from './pages/BusinessProfile';
import WidgetSettings from './pages/WidgetSettings';
import SmsSettings from './pages/SmsSettings';
import TelephonySettings from './pages/TelephonySettings';
import EmailSettings from './pages/EmailSettings';
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
            <Route path="contacts" element={<Contacts />} />
            <Route path="contacts/:id" element={<ContactDetail />} />
            <Route path="calls" element={<Calls />} />
            <Route path="analytics/unknowns" element={<UnknownLeads />} />
            <Route path="analytics/unknowns/:id" element={<UnknownLeadDetail />} />
            <Route path="analytics/usage" element={<Plots />} />
            <Route path="analytics/plots" element={<Navigate to="/analytics/usage" replace />} />

            {/* Settings routes */}
            <Route path="settings" element={<Navigate to="/settings/prompts" replace />} />
            <Route path="settings/prompts" element={<Prompts />} />
            <Route path="settings/prompts/wizard" element={<PromptWizard />} />
            <Route path="settings/widget" element={<WidgetSettings />} />
            <Route path="settings/email" element={<EmailSettings />} />
            <Route path="settings/sms" element={<SmsSettings />} />
            <Route path="settings/telephony" element={<TelephonySettings />} />
            <Route path="telephony-settings" element={<Navigate to="/settings/telephony" replace />} />
            <Route path="sms" element={<Navigate to="/settings/sms" replace />} />
            <Route path="settings/profile" element={<BusinessProfile />} />

            {/* Redirects for backward compatibility */}
            <Route path="prompts" element={<Navigate to="/settings/prompts" replace />} />
            <Route path="prompts/wizard" element={<Navigate to="/settings/prompts/wizard" replace />} />
            <Route path="email" element={<Navigate to="/settings/email" replace />} />

            <Route path="admin/tenants" element={<ManageTenants />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
