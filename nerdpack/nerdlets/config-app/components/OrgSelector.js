import React from 'react';
import { NrqlQuery, Spinner, Select, SelectItem } from 'nr1';

export default function OrgSelector({ accountId, selectedOrgId, onOrgChange }) {
  if (!accountId) return null;
  return (
    <NrqlQuery
      accountIds={[accountId]}
      query="SELECT uniques(org_id, 100) FROM MerakiConfigSnapshot SINCE 30 days ago"
    >
      {({ data, loading }) => {
        if (loading) return <Spinner />;
        const orgIds = data?.[0]?.data?.[0]?.['uniques.org_id'] || [];
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
