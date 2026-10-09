/**
 * Front-end import contracts, the same shape as the backend's: tiers (app over nouns over kernel and the
 * generated client), nouns independent of each other, roles inside a noun in one direction, and one
 * network path. Every rule here was shown failing on a planted violation before it was committed.
 */
const NOUN = "^src/nouns/([^/]+)/";

module.exports = {
  forbidden: [
    {
      name: "no-cycles",
      severity: "error",
      comment: "A ring of imports makes every module in it load, test and move together.",
      from: {},
      to: { circular: true },
    },
    {
      name: "tiers-kernel-is-the-floor",
      severity: "error",
      comment: "The kernel (design system, http, auth) imports no noun and no app module.",
      from: { path: "^src/kernel/" },
      to: { path: "^src/(nouns|app)/" },
    },
    {
      name: "tiers-nouns-never-import-the-app",
      severity: "error",
      comment: "Pages that compose several nouns live in app/; a noun never reaches up into it.",
      from: { path: "^src/nouns/" },
      to: { path: "^src/app/" },
    },
    {
      name: "nouns-are-independent",
      severity: "error",
      comment: "A noun never imports another noun; compose them in app/.",
      from: { path: NOUN },
      to: { path: "^src/nouns/", pathNot: "^src/nouns/$1/" },
    },
    {
      name: "app-reaches-nouns-through-routes-and-ui",
      severity: "error",
      comment: "app/ uses a noun's routes and ui, never its api or state directly.",
      from: { path: "^src/app/" },
      to: { path: "^src/nouns/[^/]+/(api|state)" },
    },
    {
      name: "roles-api-is-the-bottom",
      severity: "error",
      comment: "Inside a noun: routes over ui over state over api.",
      from: { path: `${NOUN}api` },
      to: { path: "^src/nouns/$1/(state|ui|routes)" },
    },
    {
      name: "roles-state-below-ui",
      severity: "error",
      from: { path: `${NOUN}state` },
      to: { path: "^src/nouns/$1/(ui|routes)" },
    },
    {
      name: "roles-ui-below-routes",
      severity: "error",
      from: { path: `${NOUN}ui` },
      to: { path: "^src/nouns/$1/routes" },
    },
    {
      name: "one-network-path",
      severity: "error",
      comment: "Only kernel/http and a noun's api role touch the generated client; nothing imports a raw HTTP library.",
      from: { pathNot: "^src/(kernel/http|nouns/[^/]+/api)" },
      to: { path: ["^src/generated/", "^node_modules/(axios|ky|node-fetch|superagent)/"] },
    },
    {
      name: "no-orphans",
      severity: "error",
      comment: "A file nothing imports is dead or an undeclared way in.",
      from: { orphan: true, pathNot: ["^src/main\\.tsx?$", "\\.d\\.ts$", "(^|/)tsconfig\\.json$"] },
      to: {},
    },
    {
      name: "no-unresolvable",
      severity: "error",
      from: {},
      to: { couldNotResolve: true },
    },
    {
      name: "no-dev-dependencies-in-src",
      severity: "error",
      from: { path: "^src/" },
      to: { dependencyTypes: ["npm-dev"] },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    tsPreCompilationDeps: true,
    tsConfig: { fileName: "tsconfig.json" },
  },
};
