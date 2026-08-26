# Architecture v1.0

## Agent runtime

The runtime uses plugin-like registration and append-only events. Each domain
declares responsibilities, inputs, outputs, and tools. The runtime owns
governance checks, human approval gates, event records, and failures.

## Marketing ontology

Initial classes include Opportunity, Audience, Customer, Journey,
ProductPackage, FareProduct, AncillaryProduct, BenefitCoupon, Campaign,
Content, Channel, Approval, and ConversionResult. Relations carry source,
evidence, confidence, and time so agents can explain recommendations and
result feedback.

## Domain boundaries

- Product module creates, approves, serves, and delivers activity products.
- Strategy module owns audience insight, snapshots, and protection rules.
- Activity module owns planning, matching, orchestration, content, approval,
  execution, feedback, and review.

