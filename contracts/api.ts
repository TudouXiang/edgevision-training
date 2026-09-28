/** Temporary T010 health-only bridge for the preserved Vue shell.
 * Authoritative schema: backend/app/schemas.py → FastAPI OpenAPI.
 * Remove this bridge and import contracts/generated/openapi.ts after
 * contract-generate can run in an environment with backend dependencies.
 */
export interface LiveResponse { status: 'ok'; service: 'api' }
export interface ReadyResponse { status: 'ready'; database: 'migrated'; storage: 'available' }
export interface FeatureCapability {
  available: boolean
  reason_code: string | null
  reason: string | null
  detected_version: string | null
}
export interface Capabilities {
  schema_version: 1
  features: Record<string, FeatureCapability>
}
