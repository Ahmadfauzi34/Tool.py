// Dead code module - never imported anywhere in the project
export interface AbandonedSchema {
  legacyId: number;
  deprecatedToken: string;
  unusedFlag: boolean;
}

export function parseAbandonedData(raw: string): AbandonedSchema {
  return {
    legacyId: 999,
    deprecatedToken: 'dead-token-' + raw,
    unusedFlag: true,
  };
}
