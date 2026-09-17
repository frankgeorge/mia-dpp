CREATE TABLE "integration_graph" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"org_id" text DEFAULT 'default' NOT NULL,
	"source_field" text NOT NULL,
	"target_element" text NOT NULL,
	"semantic_id" text NOT NULL,
	"verified_at" timestamp DEFAULT now() NOT NULL,
	"corrections" integer DEFAULT 1 NOT NULL
);
--> statement-breakpoint
CREATE TABLE "org_settings" (
	"org_id" text PRIMARY KEY NOT NULL,
	"org_name" text,
	"logo_url" text,
	"brand_color" text DEFAULT '#0B5FD0',
	"sap_host" text,
	"sap_client" text DEFAULT '100',
	"sap_username" text,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "passports" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"passport_id" text NOT NULL,
	"org_id" text DEFAULT 'default' NOT NULL,
	"product_name" text NOT NULL,
	"product_url" text,
	"submodel_id" text DEFAULT 'nameplate' NOT NULL,
	"status" text DEFAULT 'draft' NOT NULL,
	"submodel" jsonb NOT NULL,
	"generated_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "passports_passport_id_unique" UNIQUE("passport_id")
);
--> statement-breakpoint
CREATE TABLE "supplier_sessions" (
	"token" text PRIMARY KEY NOT NULL,
	"org_id" text DEFAULT 'default' NOT NULL,
	"product_name" text NOT NULL,
	"product_url" text DEFAULT '' NOT NULL,
	"contact_email" text NOT NULL,
	"gaps" jsonb NOT NULL,
	"branding" jsonb,
	"response" jsonb,
	"responded" boolean DEFAULT false NOT NULL,
	"responded_at" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"expires_at" timestamp NOT NULL
);
