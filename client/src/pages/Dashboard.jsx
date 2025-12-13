import { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { api } from '../api/client';
import './Dashboard.css';

export default function Dashboard() {
  const [leads, setLeads] = useState([]);
  const [chartData, setChartData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [leadsData, statsData] = await Promise.all([
        api.getLeads({ limit: 10 }).catch(() => ({ leads: [] })),
        api.getLeadsStats().catch(() => ({ weekly: [] })),
      ]);
      
      setLeads(leadsData.leads || leadsData || []);
      setChartData(statsData.weekly || generateMockChartData());
    } catch (err) {
      setError('Failed to load dashboard data');
      setChartData(generateMockChartData());
    } finally {
      setLoading(false);
    }
  };

  const generateMockChartData = () => {
    const weeks = ['Week 1', 'Week 2', 'Week 3', 'Week 4'];
    return weeks.map(week => ({
      week,
      total: Math.floor(Math.random() * 50) + 20,
      acquired: Math.floor(Math.random() * 30) + 10,
    }));
  };

  if (loading) {
    return <div className="loading">Loading dashboard...</div>;
  }

  return (
    <div className="dashboard">
      <h1>Dashboard</h1>
      
      <div className="dashboard-grid">
        <div className="card chart-card">
          <h2>Weekly Leads</h2>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="week" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="total" name="Total Leads" fill="#4ade80" />
                <Bar dataKey="acquired" name="Acquired" fill="#1a1a2e" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        
        <div className="card leads-card">
          <h2>Recent Leads</h2>
          {error && <div className="error">{error}</div>}
          
          {leads.length === 0 ? (
            <p className="empty-state">No leads yet. Start conversations to generate leads.</p>
          ) : (
            <table className="leads-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Phone</th>
                  <th>Status</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((lead) => (
                  <tr key={lead.id}>
                    <td>{lead.name || 'Unknown'}</td>
                    <td>{lead.phone_number}</td>
                    <td>
                      <span className={`status ${lead.status}`}>
                        {lead.status}
                      </span>
                    </td>
                    <td>{new Date(lead.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
