DevOps is a way for people who develop software and people who operate it
to work together. They share responsibility for delivering changes and
keeping services useful and reliable. Automation and feedback support
that work; buying a tool alone does not create a DevOps practice.

## Follow a change

Imagine a team improves a cloud-hosted journal application:

1. A developer records a change in **version control**, a history of files
   that helps the team review and recover changes.
2. An automated **continuous integration** (CI) process builds and tests
   the change. Continuous delivery keeps the change ready for release;
   continuous deployment can release changes automatically after checks.
3. The team describes cloud resources with **infrastructure as code**
   (IaC). They review those definitions and use tools to apply them
   consistently.
4. The application runs in a **container**, a package containing the
   application and its dependencies. **Kubernetes** can coordinate
   containers across machines, including replacing failed instances.
5. After release, the team uses **observability** to understand the
   service. Metrics show measurements over time, logs record events, and
   traces follow a request through components.

These are examples, not mandatory tools for every team. A small service
may not need Kubernetes. People still review changes, respond to problems,
and decide what to improve.

## Why it helps

Small, reviewed changes and automated tests can catch problems earlier.
Repeatable deployments reduce manual mistakes. Monitoring and feedback
help a team notice a problem, investigate it, and improve the next release.
No process guarantees that failures will never happen.

## Check your understanding

Suppose a release passes its tests but users report slow responses. Which
part of the workflow helps the team investigate the running service?
Observability can provide measurements, events, and request traces. The
team can use those clues to find the cause and make a new change.

## Go deeper

These resources are optional:

- [What is Infrastructure as Code?](https://www.hashicorp.com/resources/what-is-infrastructure-as-code)
- [What is Kubernetes?](https://kubernetes.io/docs/concepts/overview/)
