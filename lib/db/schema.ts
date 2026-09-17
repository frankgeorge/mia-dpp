import {
  pgTable,
  text,
  timestamp,
  jsonb,
  integer,
  real,
  boolean,
  uuid,
} from "drizzle-orm/pg-core";

// ── Passports ──────────────────────────────────────────────────────────────
// One row per generated Digital Product Passport.

export const passports = pgTable("passports", {
  id: uuid("id").primaryKey().defaultRandom(),
  passportId: text("passport_id").notNull().unique(), // urn:dpp:...
  orgId: text("org_id").notNull().default("default"), // replaced by real org when auth added
  productName: text("product_name").notNull(),
  productUrl: text("product_url"),
  submodelId: text("submodel_id").notNull().default("nameplate"),
  status: text("status").notNull().default("draft"), // draft | complete
  submodel: jsonb("submodel").notNull(),             // full AAS JSON
  generatedAt: timestamp("generated_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
});

// ── Integration Graph ──────────────────────────────────────────────────────
// Verified source→target mappings shared across all products in an org.

export const integrationGraph = pgTable("integration_graph", {
  id: uuid("id").primaryKey().defaultRandom(),
  orgId: text("org_id").notNull().default("default"),
  sourceField: text("source_field").notNull(),
  targetElement: text("target_element").notNull(),
  semanticId: text("semantic_id").notNull(),
  verifiedAt: timestamp("verified_at").notNull().defaultNow(),
  corrections: integer("corrections").notNull().default(1),
});

// ── Supplier Sessions ──────────────────────────────────────────────────────
// Created when MIA emails a supplier; resolved when supplier submits the form.

export const supplierSessions = pgTable("supplier_sessions", {
  token: text("token").primaryKey(),
  orgId: text("org_id").notNull().default("default"),
  productName: text("product_name").notNull(),
  productUrl: text("product_url").notNull().default(""),
  contactEmail: text("contact_email").notNull(),
  gaps: jsonb("gaps").notNull(),        // GapField[]
  branding: jsonb("branding"),          // OrgBranding | null
  response: jsonb("response"),          // Record<string,string> | null
  responded: boolean("responded").notNull().default(false),
  respondedAt: timestamp("responded_at"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  expiresAt: timestamp("expires_at").notNull(),
});

// ── Org Settings ───────────────────────────────────────────────────────────
// Per-org branding and SAP connector config (passwords server-side only).

export const orgSettings = pgTable("org_settings", {
  orgId: text("org_id").primaryKey(),
  orgName: text("org_name"),
  logoUrl: text("logo_url"),
  brandColor: text("brand_color").default("#0B5FD0"),
  sapHost: text("sap_host"),
  sapClient: text("sap_client").default("100"),
  sapUsername: text("sap_username"),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
});
