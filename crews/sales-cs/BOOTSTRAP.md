# Sales-CS Bootstrap

This one-time bootstrap collects the product/service handbook and operational context before customer service work starts. Main agent（小贝）should ask these questions on behalf of this crew and write the answers into the crew workspace.

## Step 1: Product/Service Handbook

Collect:

- **Product name**: full product/service name
- **Core value**: one-line description of what problem it solves for customers
- **Target customers**: typical customer profile
- **Pricing tiers**: each tier's name, price, target audience, and core benefits
- **Purchase method**: how customers buy (payment link, QR code, contact person, etc.)
- **FAQ**: top 5-10 frequently asked questions and their answers

## Step 2: Operational Links

Collect:

- Feedback survey URL
- Invoice request form URL
- Purchase page URL
- Trial/experience application URL (if applicable)

## Step 3: Escalation Contact

Collect:

- Human escalation WeChat ID (for complex issues, complaints, refund requests)
- Any other escalation channels

## Step 4: Environment Verification

On first startup, check and report:

1. Customer database is initialized: `./skills/customer-db/scripts/init-db.sh` (idempotent)
2. Follow-up table is ready: `./skills/customer-db/scripts/follow-up-init.sh` (idempotent)

## Completion

After bootstrap is complete:

1. Update `MEMORY.md` with the full product/service handbook, key links, and escalation contact — replacing all placeholder entries.
2. Update `USER.md` if needed with service-specific notes.
3. Delete `BOOTSTRAP.md` from the runtime workspace.
4. Suggest the next step, such as testing a sample customer conversation.
