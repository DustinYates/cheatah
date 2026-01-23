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
import Plots from './pages/Plots';
import ConversationAnalytics from './pages/ConversationAnalytics';
import WidgetAnalytics from './pages/WidgetAnalytics';
import Onboarding from './pages/Onboarding';
import BusinessProfile from './pages/BusinessProfile';
import WidgetSettings from './pages/WidgetSettings';
import SmsSettings from './pages/SmsSettings';
import TelephonySettings from './pages/TelephonySettings';
import EmailSettings from './pages/EmailSettings';
import EscalationSettings from './pages/EscalationSettings';
import ManageTenants from './pages/ManageTenants';
import PromptWizard from './pages/PromptWizard';
import PrivacyPolicy from './pages/PrivacyPolicy';
import TermsOfService from './pages/TermsOfService';
import './App.css';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/privacy" element={<PrivacyPolicy />} />
          <Route path="/terms" element={<TermsOfService />} />
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
            <Route path="analytics/usage" element={<Plots />} />
            <Route path="analytics/conversations" element={<ConversationAnalytics />} />
            <Route path="analytics/widget" element={<WidgetAnalytics />} />
            <Route path="analytics/plots" element={<Navigate to="/analytics/usage" replace />} />

            {/* Settings routes */}
            <Route path="settings" element={<Navigate to="/settings/prompts" replace />} />
            <Route path="settings/prompts" element={<Prompts />} />
            <Route path="settings/prompts/wizard" element={<PromptWizard />} />
            <Route path="settings/widget" element={<WidgetSettings />} />
            <Route path="settings/email" element={<EmailSettings />} />
            <Route path="settings/sms" element={<SmsSettings />} />
            <Route path="settings/telephony" element={<TelephonySettings />} />
            <Route path="settings/escalation" element={<EscalationSettings />} />
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
