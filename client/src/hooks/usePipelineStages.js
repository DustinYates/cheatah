import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';

const DEFAULT_STAGES = [
  { key: 'new_lead', label: 'New Lead', color: '#1d4ed8', position: 0 },
  { key: 'contacted', label: 'Contacted', color: '#b45309', position: 1 },
  { key: 'interested', label: 'Interested', color: '#be185d', position: 2 },
  { key: 'registered', label: 'Registered', color: '#047857', position: 3 },
  { key: 'enrolled', label: 'Enrolled', color: '#4338ca', position: 4 },
];

// Module-level cache shared across all components
let cachedStages = null;
let cachedTenantId = null;
let fetchPromise = null;

export function usePipelineStages() {
  const [stages, setStages] = useState(cachedStages || DEFAULT_STAGES);
  const [loading, setLoading] = useState(!cachedStages);

  const fetchStages = useCallback(async () => {
    const currentTenantId = api.getSelectedTenant?.() ?? null;

    if (cachedStages && cachedTenantId === currentTenantId) {
      setStages(cachedStages);
      setLoading(false);
      return cachedStages;
    }

    // Deduplicate concurrent fetches
    if (fetchPromise) {
      const result = await fetchPromise;
      setStages(result);
      setLoading(false);
      return result;
    }

    setLoading(true);
    fetchPromise = api.getPipelineStages()
      .then((data) => {
        const result = data.stages?.length ? data.stages : DEFAULT_STAGES;
        cachedStages = result;
        cachedTenantId = currentTenantId;
        return result;
      })
      .catch(() => DEFAULT_STAGES)
      .finally(() => { fetchPromise = null; });

    const result = await fetchPromise;
    setStages(result);
    setLoading(false);
    return result;
  }, []);

  const invalidate = useCallback(() => {
    cachedStages = null;
    cachedTenantId = null;
  }, []);

  useEffect(() => {
    fetchStages();
  }, [fetchStages]);

  // Build lookup helpers
  const stageMap = {};
  const stageLabelMap = {};
  for (const s of stages) {
    stageMap[s.key] = s;
    stageLabelMap[s.key] = s.label;
  }

  return { stages, loading, refetch: fetchStages, invalidate, stageMap, stageLabelMap };
}
