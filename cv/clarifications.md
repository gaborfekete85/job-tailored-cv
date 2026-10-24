# Clarifications

Answers given in the CV tailoring UI, grouped by work period. Every answer is evidence for future jobs — edit or delete freely. Each `  - ` line under a question is one fact.

## 2022-06 – 2025-07 · Lead Developer · Fintama AG (client: Julius Baer)

### 2026-10-19 · Axpo Group — Staff AI Platform Engineer (f/m/d) · M1: Several years of solid backend and infrastructure engineering, building and operating production systems

- **Q:** What production load did your 5 microservices handle (e.g., requests or Kafka events per day, number of client accounts or transactions processed)?
  - Introduced auto-scaling to handle the undeterministic load from Singapore to the USA with around 10K users all in all
- **Q:** What problem led you to introduce the Dead Letter Queue? For example, lost or stuck messages, manual reprocessing, or recurring incidents. What measurably improved afterwards, such as fewer incidents, faster recovery or less manual effort?
  - Introduced a dead letter monitoring approach that decreased the lost/failed event production issue investigation time by 50% ... the prod issue ticket numbers to nearly 0.
- **Q:** On the Kubernetes environments, what infrastructure work did you do yourself (e.g., writing deployment manifests or Helm charts, configuring scaling or resources, managing secrets), and across how many environments or clusters?
  - With the Prod Kubernetes infrastructure team optimized the resource consumption and cost of the application operation by 40%
- **Q:** Were you on call or in a production support rotation for these services? If so, roughly how many incidents did you handle, and did availability or mean time to resolve improve (before vs. after)?
  - Before, the dead letter monitoring service usually the investigation took 2 - 3 hours per a day which could be automated to nearly 0.
- **Q:** How often did your team deploy to production under the bank's release governance, and did your CI/CD work change that frequency or shorten lead time?
  - Production deployment in every 2 weeks

### 2026-10-19 · Axpo Group — Staff AI Platform Engineer (f/m/d) · M8: Write reasonable frontend code (or keen to learn it)

- **Q:** At Julius Baer (2022–2025), did you write or change any frontend code (e.g. Angular, React, JSP, internal admin UIs), or did your team's 5 microservices have no UI at all?
  - Implemented complete front to back stories with REACT in case of short of Frontend developers like sickness or vacation.
- **Q:** If you touched the frontend: which framework/language did you use, and which screens or features did you build or maintain (e.g. forms, dashboards, internal tools)?
  - Implemented dashboard related filter functionalities and user actions
- **Q:** Roughly how much of your time went to frontend work there (e.g. occasional fixes vs. a full feature end-to-end), and how many users or which business teams used that UI?
  - Occasional needs were applied to jump in the frontend role ... Which is fully fitting in my mindset to work end to end
- **Q:** Did you work directly with frontend developers or UX designers, for example by defining the REST API contracts their UI consumed or by reviewing their code?
  - Yes during the planning worked closely with the team aligning the contract ... also implemented a frontend stub backend from Openapi contract enabling the frontend team working paralelly with the backend implementation.
