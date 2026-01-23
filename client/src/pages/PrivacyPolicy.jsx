import React from 'react';
import './Legal.css';

const PrivacyPolicy = () => {
  return (
    <div className="legal-page">
      <div className="legal-container">
        <h1>Privacy Policy</h1>
        <p className="last-updated">Last Updated: January 2025</p>

        <section>
          <h2>1. Introduction</h2>
          <p>
            This Privacy Policy describes how ChatterCheetah ("we", "us", or "our") collects,
            uses, and protects your personal information when you use our AI-powered customer
            communication platform.
          </p>
        </section>

        <section>
          <h2>2. Information We Collect</h2>

          <h3>2.1 Account Information</h3>
          <p>When you create an account, we collect:</p>
          <ul>
            <li>Email address</li>
            <li>Name</li>
            <li>Business information</li>
            <li>Phone number (if provided)</li>
          </ul>

          <h3>2.2 Chat and Communication Data</h3>
          <p>When you or your customers use our services, we collect:</p>
          <ul>
            <li>Chat messages and conversation history</li>
            <li>SMS messages sent through our platform</li>
            <li>Email communications</li>
            <li>Contact information of leads and customers</li>
          </ul>

          <h3>2.3 Usage and Technical Data</h3>
          <p>We automatically collect:</p>
          <ul>
            <li>Session information and timestamps</li>
            <li>Browser type and device information</li>
            <li>IP addresses</li>
            <li>Widget interaction data</li>
          </ul>
        </section>

        <section>
          <h2>3. How We Use Your Information</h2>
          <p>We use your information to:</p>
          <ul>
            <li>Provide and improve our AI chat services</li>
            <li>Process and deliver SMS and email communications</li>
            <li>Analyze usage patterns and optimize performance</li>
            <li>Provide customer support</li>
            <li>Send service-related notifications</li>
            <li>Ensure security and prevent fraud</li>
          </ul>
        </section>

        <section>
          <h2>4. Third-Party Services</h2>
          <p>We use the following third-party services to operate our platform:</p>
          <ul>
            <li><strong>Google AI (Gemini)</strong> - For AI-powered chat responses</li>
            <li><strong>Telnyx</strong> - For SMS messaging services</li>
            <li><strong>SendGrid</strong> - For email delivery</li>
            <li><strong>Sentry</strong> - For error tracking and performance monitoring</li>
            <li><strong>Supabase</strong> - For database and authentication services</li>
          </ul>
          <p>
            Each of these services has their own privacy policies governing how they handle data.
          </p>
        </section>

        <section>
          <h2>5. Data Retention</h2>
          <p>
            We retain your data for as long as your account is active or as needed to provide
            you services. Conversation data is retained according to your account settings.
            You may request deletion of your data at any time.
          </p>
        </section>

        <section>
          <h2>6. Your Rights</h2>
          <p>You have the right to:</p>
          <ul>
            <li><strong>Access</strong> - Request a copy of your personal data</li>
            <li><strong>Correction</strong> - Request correction of inaccurate data</li>
            <li><strong>Deletion</strong> - Request deletion of your personal data</li>
            <li><strong>Portability</strong> - Request your data in a portable format</li>
            <li><strong>Opt-out</strong> - Unsubscribe from marketing communications</li>
          </ul>
        </section>

        <section>
          <h2>7. Data Security</h2>
          <p>
            We implement industry-standard security measures to protect your data, including:
          </p>
          <ul>
            <li>Encryption of data in transit (HTTPS/TLS)</li>
            <li>Secure database storage</li>
            <li>Access controls and authentication</li>
            <li>Regular security audits</li>
          </ul>
        </section>

        <section>
          <h2>8. Cookies</h2>
          <p>
            We use essential cookies to maintain your session and provide our services.
            We do not use third-party tracking cookies for advertising purposes.
          </p>
        </section>

        <section>
          <h2>9. Changes to This Policy</h2>
          <p>
            We may update this Privacy Policy from time to time. We will notify you of any
            changes by posting the new policy on this page and updating the "Last Updated" date.
          </p>
        </section>

        <section>
          <h2>10. Contact Us</h2>
          <p>
            If you have any questions about this Privacy Policy or wish to exercise your
            data rights, please contact us at:
          </p>
          <p className="contact-info">
            Email: privacy@chattercheetah.com
          </p>
        </section>
      </div>
    </div>
  );
};

export default PrivacyPolicy;
