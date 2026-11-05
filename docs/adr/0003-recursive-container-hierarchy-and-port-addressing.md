# Recursive Container Hierarchy and Dynamic Port Addressing

Beamlines use diverse physical sample containment (shipping dewars, pucks, canes, cassettes, and plates) and automation layouts. We decided to model all containment through a single recursive `Container` model with self-referencing parents and geometric envelope definitions, computing robot port coordinates dynamically through path traversal rather than hardcoding vessel schemas.
