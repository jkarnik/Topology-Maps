import React from 'react';
import { NrqlQuery, Spinner, Select, SelectItem } from 'nr1';

export default function OrgSelector({ accountId, selectedOrgId, onOrgChange }) {
  if (!accountId) return null;
  return (
    <NrqlQuery
      accountIds={[accountId]}
      query="SELECT count(*) FROM MerakiConfigSnapshot FACET org_id SINCE 30 days ago LIMIT 100"
    >
      {({ data, loading, error }) => {
        if (loading) return <Spinner />;
        if (error) return <p style={{color:'red'}}>Query error: {error.message}</p>;
        const orgIds = (data || []).map(s => s.metadata?.groups?.find(g => g.type === 'facet')?.value).filter(Boolean);
        if (orgIds.length === 0) return <p style={{color:'orange'}}>No orgs found (accountId: {accountId})</p>;
        return (
          <Select value={selectedOrgId} onChange={(_, value) => onOrgChange(value)} label="Organization">
            <SelectItem value={null}>— Select org —</SelectItem>
            {orgIds.map((id) => <SelectItem key={id} value={id}>{id}</SelectItem>)}
          </Select>
        );
      }}
    </NrqlQuery>
  );
}
