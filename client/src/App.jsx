import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import Login from './pages/Login';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import Dashboard from './pages/Dashboard';
import Kanban from './pages/Kanban';
import Prompts from './pages/Prompts';
import Contacts from './pages/Contacts';
import ContactDetail from './pages/ContactDetail';
import Customers from './pages/Customers';
import CustomerDetail from './pages/CustomerDetail';
import CustomerSupportSettings from './pages/CustomerSupportSettings';
import Calls from './pages/Calls';
import Inbox from './pages/Inbox';
import Plots from './pages/Plots';
import ConversationAnalytics from './pages/ConversationAnalytics';
import WidgetAnalytics from './pages/WidgetAnalytics';
import SavingsAnalytics from './pages/SavingsAnalytics';
import CommunicationsHealth from './pages/CommunicationsHealth';
import CustomerHappiness from './pages/CustomerHappiness';
import TopicAnalytics from './pages/TopicAnalytics';
import VoiceABTestAnalytics from './pages/VoiceABTestAnalytics';
import Onboarding from './pages/Onboarding';
import BusinessProfile from './pages/BusinessProfile';
import WidgetSettings from './pages/WidgetSettings';
import SmsSettings from './pages/SmsSettings';
import TelephonySettings from './pages/TelephonySettings';
import EmailSettings from './pages/EmailSettings';
import CampaignSettings from './pages/CampaignSettings';
import EscalationSettings from './pages/EscalationSettings';
import CalendarSettings from './pages/CalendarSettings';
import DncList from './pages/DncList';
import ManageTenants from './pages/ManageTenants';
import PromptWizard from './pages/PromptWizard';
import PrivacyPolicy from './pages/PrivacyPolicy';
import TermsOfService from './pages/TermsOfService';
import Forums from './pages/Forums';
import ForumDetail from './pages/ForumDetail';
import ForumPost from './pages/ForumPost';
import NewForumPost from './pages/NewForumPost';
import AccountSettings from './pages/AccountSettings';
import Support from './pages/Support';
import UsageBilling from './pages/UsageBilling';
import './App.css';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
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
            <Route path="kanban" element={<Kanban />} />
            <Route path="contacts" element={<Contacts />} />
            <Route path="contacts/:id" element={<ContactDetail />} />
            <Route path="customers" element={<Customers />} />
            <Route path="customers/:id" element={<CustomerDetail />} />
            <Route path="inbox" element={<Inbox />} />
            <Route path="calls" element={<Calls />} />
            <Route path="analytics/usage" element={<Plots />} />
            <Route path="analytics/conversations" element={<ConversationAnalytics />} />
            <Route path="analytics/widget" element={<WidgetAnalytics />} />
            <Route path="analytics/savings" element={<SavingsAnalytics />} />
            <Route path="analytics/health" element={<CommunicationsHealth />} />
            <Route path="analytics/happiness" element={<CustomerHappiness />} />
            <Route path="analytics/topics" element={<TopicAnalytics />} />
            <Route path="analytics/voice-ab" element={<VoiceABTestAnalytics />} />
            <Route path="analytics/plots" element={<Navigate to="/analytics/usage" replace />} />

            {/* Settings routes */}
            <Route path="settings" element={<Navigate to="/settings/prompts" replace />} />
            <Route path="settings/prompts" element={<Prompts />} />
            <Route path="settings/prompts/wizard" element={<PromptWizard />} />
            <Route path="settings/chatbot" element={<WidgetSettings />} />
            <Route path="settings/email" element={<EmailSettings />} />
            <Route path="settings/sms" element={<SmsSettings />} />
            <Route path="settings/telephony" element={<TelephonySettings />} />
            <Route path="settings/escalation" element={<EscalationSettings />} />
            <Route path="settings/calendar" element={<CalendarSettings />} />
            <Route path="settings/dnc" element={<DncList />} />
            <Route path="settings/campaigns" element={<CampaignSettings />} />
            <Route path="settings/customer-support" element={<CustomerSupportSettings />} />
            <Route path="settings/profile" element={<BusinessProfile />} />
            <Route path="settings/account" element={<AccountSettings />} />

            {/* Redirects for backward compatibility */}
            <Route path="settings/widget" element={<Navigate to="/settings/chatbot" replace />} />
            <Route path="telephony-settings" element={<Navigate to="/settings/telephony" replace />} />
            <Route path="sms" element={<Navigate to="/settings/sms" replace />} />
            <Route path="prompts" element={<Navigate to="/settings/prompts" replace />} />
            <Route path="prompts/wizard" element={<Navigate to="/settings/prompts/wizard" replace />} />
            <Route path="email" element={<Navigate to="/settings/email" replace />} />

            {/* Forum routes */}
            <Route path="forums" element={<Forums />} />
            <Route path="forums/:forumSlug" element={<ForumDetail />} />
            <Route path="forums/:forumSlug/:categorySlug" element={<ForumDetail />} />
            <Route path="forums/:forumSlug/:categorySlug/new" element={<NewForumPost />} />
            <Route path="forums/:forumSlug/:categorySlug/:postId" element={<ForumPost />} />

            <Route path="billing" element={<UsageBilling />} />
            <Route path="support" element={<Support />} />
            <Route path="admin/tenants" element={<ManageTenants />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
