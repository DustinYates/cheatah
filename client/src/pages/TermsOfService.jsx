import React from 'react';
import './Legal.css';

const TermsOfService = () => {
  return (
    <div className="legal-page">
      <div className="legal-container">
        <h1>Terms of Service</h1>
        <p className="last-updated">Last Updated: January 2025</p>

        <section>
          <h2>1. Acceptance of Terms</h2>
          <p>
            By accessing or using ChatterCheetah ("Service"), you agree to be bound by these
            Terms of Service. If you do not agree to these terms, please do not use our Service.
          </p>
        </section>

        <section>
          <h2>2. Description of Service</h2>
          <p>
            ChatterCheetah is an AI-powered customer communication platform that provides:
          </p>
          <ul>
            <li>AI chatbot widgets for websites</li>
            <li>SMS messaging capabilities</li>
            <li>Email communication tools</li>
            <li>Lead capture and management</li>
            <li>Conversation analytics</li>
          </ul>
        </section>

        <section>
          <h2>3. Account Registration</h2>
          <p>
            To use our Service, you must create an account and provide accurate, complete
            information. You are responsible for:
          </p>
          <ul>
            <li>Maintaining the confidentiality of your account credentials</li>
            <li>All activities that occur under your account</li>
            <li>Notifying us immediately of any unauthorized access</li>
          </ul>
        </section>

        <section>
          <h2>4. Acceptable Use</h2>
          <p>You agree NOT to use the Service to:</p>
          <ul>
            <li>Send spam or unsolicited messages</li>
            <li>Violate any applicable laws or regulations</li>
            <li>Infringe on intellectual property rights</li>
            <li>Transmit malicious code or harmful content</li>
            <li>Harass, abuse, or harm others</li>
            <li>Impersonate any person or entity</li>
            <li>Interfere with the Service's operation</li>
          </ul>
        </section>

        <section>
          <h2>5. SMS and Communication Compliance</h2>
          <p>
            When using our SMS features, you agree to comply with all applicable laws including:
          </p>
          <ul>
            <li>Telephone Consumer Protection Act (TCPA)</li>
            <li>CAN-SPAM Act</li>
            <li>Carrier guidelines and requirements</li>
          </ul>
          <p>
            You are responsible for obtaining proper consent before sending messages to recipients.
          </p>
        </section>

        <section>
          <h2>6. AI-Generated Content</h2>
          <p>
            Our Service uses artificial intelligence to generate responses. You acknowledge that:
          </p>
          <ul>
            <li>AI responses may not always be accurate or appropriate</li>
            <li>You are responsible for reviewing and training your AI chatbot</li>
            <li>AI-generated content should be verified before critical decisions</li>
          </ul>
        </section>

        <section>
          <h2>7. Intellectual Property</h2>
          <p>
            The Service and its original content, features, and functionality are owned by
            ChatterCheetah and are protected by copyright, trademark, and other intellectual
            property laws.
          </p>
          <p>
            You retain ownership of any content you provide through the Service.
          </p>
        </section>

        <section>
          <h2>8. Service Availability</h2>
          <p>
            We strive to maintain high availability but do not guarantee uninterrupted access.
            We may modify, suspend, or discontinue any aspect of the Service with reasonable notice.
          </p>
        </section>

        <section>
          <h2>9. Limitation of Liability</h2>
          <p>
            TO THE MAXIMUM EXTENT PERMITTED BY LAW, CHATTERCHEETAH SHALL NOT BE LIABLE FOR:
          </p>
          <ul>
            <li>Indirect, incidental, special, or consequential damages</li>
            <li>Loss of profits, data, or business opportunities</li>
            <li>Damages arising from AI-generated content</li>
            <li>Third-party actions or content</li>
          </ul>
          <p>
            Our total liability shall not exceed the amount paid by you in the twelve months
            preceding the claim.
          </p>
        </section>

        <section>
          <h2>10. Indemnification</h2>
          <p>
            You agree to indemnify and hold harmless ChatterCheetah from any claims, damages,
            or expenses arising from your use of the Service or violation of these Terms.
          </p>
        </section>

        <section>
          <h2>11. Termination</h2>
          <p>
            We may terminate or suspend your account at any time for violations of these Terms.
            You may terminate your account at any time by contacting us. Upon termination,
            your right to use the Service ceases immediately.
          </p>
        </section>

        <section>
          <h2>12. Changes to Terms</h2>
          <p>
            We reserve the right to modify these Terms at any time. We will provide notice of
            significant changes. Continued use of the Service after changes constitutes
            acceptance of the new Terms.
          </p>
        </section>

        <section>
          <h2>13. Governing Law</h2>
          <p>
            These Terms shall be governed by and construed in accordance with the laws of the
            United States, without regard to conflict of law provisions.
          </p>
        </section>

        <section>
          <h2>14. Contact Us</h2>
          <p>
            If you have any questions about these Terms of Service, please contact us at:
          </p>
          <p className="contact-info">
            Email: legal@chattercheetah.com
          </p>
        </section>
      </div>
    </div>
  );
};

export default TermsOfService;
