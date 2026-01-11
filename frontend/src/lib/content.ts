import type { Phase, Topic } from './types';

// Import all phase index files
import phase0Index from '../../content/phases/phase0/index.json';
import phase1Index from '../../content/phases/phase1/index.json';
import phase2Index from '../../content/phases/phase2/index.json';
import phase3Index from '../../content/phases/phase3/index.json';
import phase4Index from '../../content/phases/phase4/index.json';
import phase5Index from '../../content/phases/phase5/index.json';

// Import Phase 0 topics
import phase0Linux from '../../content/phases/phase0/linux.json';
import phase0Networking from '../../content/phases/phase0/networking.json';
import phase0Programming from '../../content/phases/phase0/programming.json';
import phase0CloudComputing from '../../content/phases/phase0/cloud-computing.json';
import phase0Devops from '../../content/phases/phase0/devops.json';
import phase0CloudEngineer from '../../content/phases/phase0/cloud-engineer.json';

// Import Phase 1 topics
import phase1VersionControl from '../../content/phases/phase1/version-control.json';
import phase1CloudCli from '../../content/phases/phase1/cloud-cli.json';
import phase1Iac from '../../content/phases/phase1/iac.json';
import phase1Ssh from '../../content/phases/phase1/ssh.json';
import phase1CliBasics from '../../content/phases/phase1/cli-basics.json';
import phase1CtfLab from '../../content/phases/phase1/ctf-lab.json';

// Import Phase 2 topics
import phase2Python from '../../content/phases/phase2/python.json';
import phase2Apis from '../../content/phases/phase2/apis.json';
import phase2Fastapi from '../../content/phases/phase2/fastapi.json';
import phase2Databases from '../../content/phases/phase2/databases.json';
import phase2GenaiApis from '../../content/phases/phase2/genai-apis.json';
import phase2PromptEngineering from '../../content/phases/phase2/prompt-engineering.json';
import phase2BuildTheApp from '../../content/phases/phase2/build-the-app.json';

// Import Phase 3 topics
import phase3VmsCompute from '../../content/phases/phase3/vms-compute.json';
import phase3SecurityIam from '../../content/phases/phase3/security-iam.json';
import phase3CloudNetworking from '../../content/phases/phase3/cloud-networking.json';
import phase3SecureRemoteAccess from '../../content/phases/phase3/secure-remote-access.json';
import phase3DatabaseDeployment from '../../content/phases/phase3/database-deployment.json';
import phase3FastapiDeployment from '../../content/phases/phase3/fastapi-deployment.json';
import phase3BillingCostManagement from '../../content/phases/phase3/billing-cost-management.json';
import phase3CloudAiServices from '../../content/phases/phase3/cloud-ai-services.json';
import phase3Capstone from '../../content/phases/phase3/capstone.json';

// Import Phase 4 topics
import phase4Containers from '../../content/phases/phase4/containers.json';
import phase4Cicd from '../../content/phases/phase4/cicd.json';
import phase4InfrastructureAsCode from '../../content/phases/phase4/infrastructure-as-code.json';
import phase4ContainerOrchestration from '../../content/phases/phase4/container-orchestration.json';
import phase4MonitoringObservability from '../../content/phases/phase4/monitoring-observability.json';
import phase4Capstone from '../../content/phases/phase4/capstone.json';

// Import Phase 5 topics
import phase5IdentityAccessManagement from '../../content/phases/phase5/identity-access-management.json';
import phase5DataProtectionSecrets from '../../content/phases/phase5/data-protection-secrets.json';
import phase5NetworkSecurity from '../../content/phases/phase5/network-security.json';
import phase5SecurityMonitoring from '../../content/phases/phase5/security-monitoring.json';
import phase5ThreatDetectionResponse from '../../content/phases/phase5/threat-detection-response.json';
import phase5Capstone from '../../content/phases/phase5/capstone.json';

// Topic maps by phase slug
const topicsByPhase: Record<string, Record<string, Topic>> = {
  phase0: {
    'linux': phase0Linux as Topic,
    'networking': phase0Networking as Topic,
    'programming': phase0Programming as Topic,
    'cloud-computing': phase0CloudComputing as Topic,
    'devops': phase0Devops as Topic,
    'cloud-engineer': phase0CloudEngineer as Topic,
  },
  phase1: {
    'version-control': phase1VersionControl as Topic,
    'cloud-cli': phase1CloudCli as Topic,
    'iac': phase1Iac as Topic,
    'ssh': phase1Ssh as Topic,
    'cli-basics': phase1CliBasics as Topic,
    'ctf-lab': phase1CtfLab as Topic,
  },
  phase2: {
    'python': phase2Python as Topic,
    'apis': phase2Apis as Topic,
    'fastapi': phase2Fastapi as Topic,
    'databases': phase2Databases as Topic,
    'genai-apis': phase2GenaiApis as Topic,
    'prompt-engineering': phase2PromptEngineering as Topic,
    'build-the-app': phase2BuildTheApp as Topic,
  },
  phase3: {
    'vms-compute': phase3VmsCompute as Topic,
    'security-iam': phase3SecurityIam as Topic,
    'cloud-networking': phase3CloudNetworking as Topic,
    'secure-remote-access': phase3SecureRemoteAccess as Topic,
    'database-deployment': phase3DatabaseDeployment as Topic,
    'fastapi-deployment': phase3FastapiDeployment as Topic,
    'billing-cost-management': phase3BillingCostManagement as Topic,
    'cloud-ai-services': phase3CloudAiServices as Topic,
    'capstone': phase3Capstone as Topic,
  },
  phase4: {
    'containers': phase4Containers as Topic,
    'cicd': phase4Cicd as Topic,
    'infrastructure-as-code': phase4InfrastructureAsCode as Topic,
    'container-orchestration': phase4ContainerOrchestration as Topic,
    'monitoring-observability': phase4MonitoringObservability as Topic,
    'capstone': phase4Capstone as Topic,
  },
  phase5: {
    'identity-access-management': phase5IdentityAccessManagement as Topic,
    'data-protection-secrets': phase5DataProtectionSecrets as Topic,
    'network-security': phase5NetworkSecurity as Topic,
    'security-monitoring': phase5SecurityMonitoring as Topic,
    'threat-detection-response': phase5ThreatDetectionResponse as Topic,
    'capstone': phase5Capstone as Topic,
  },
};

// Phase index type from JSON
interface PhaseIndex {
  id: number;
  name: string;
  slug: string;
  description: string;
  short_description?: string;
  estimated_weeks: string;
  order: number;
  prerequisites: string[];
  objectives?: string[];
  topics: string[]; // slug references
}

const phaseIndices: PhaseIndex[] = [
  phase0Index as PhaseIndex,
  phase1Index as PhaseIndex,
  phase2Index as PhaseIndex,
  phase3Index as PhaseIndex,
  phase4Index as PhaseIndex,
  phase5Index as PhaseIndex,
];

/**
 * Build a full Phase object from index + topic files
 */
function buildPhase(index: PhaseIndex): Phase {
  const phaseTopics = topicsByPhase[index.slug] || {};
  const topics: Topic[] = index.topics
    .map((slug) => phaseTopics[slug])
    .filter((t): t is Topic => t !== undefined);

  return {
    id: index.id,
    name: index.name,
    slug: index.slug,
    description: index.description,
    short_description: index.short_description || index.description,
    estimated_weeks: index.estimated_weeks,
    order: index.order,
    prerequisites: index.prerequisites,
    objectives: index.objectives || [],
    topics,
  };
}

/**
 * Get all phases with their topics
 */
export function getAllPhases(): Phase[] {
  return phaseIndices.map(buildPhase);
}

/**
 * Get a phase by its slug
 */
export function getPhaseBySlug(slug: string): Phase | null {
  const index = phaseIndices.find((p) => p.slug === slug);
  if (!index) return null;
  return buildPhase(index);
}

/**
 * Get a topic by phase slug and topic slug
 */
export function getTopicBySlug(phaseSlug: string, topicSlug: string): Topic | null {
  const phaseTopics = topicsByPhase[phaseSlug];
  if (!phaseTopics) return null;
  return phaseTopics[topicSlug] || null;
}
