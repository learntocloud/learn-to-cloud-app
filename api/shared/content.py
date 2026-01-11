"""Static content for Learn to Cloud phases, topics, and checklists."""

from .schemas import Phase, Topic, ChecklistItem, LearningStep, TopicChecklistItem

PHASES: list[Phase] = [
    Phase(
        id=0,
        name="Starting from Zero",
        slug="phase0",
        description="If you have zero tech experience and want to get into Cloud Engineering, this phase is for you. Take your time with these foundational concepts—understanding them well will make everything else easier.",
        estimated_weeks="3-4 weeks",
        order=0,
        prerequisites=[],
        topics=[
            Topic(
                id="phase0-topic1",
                slug="linux",
                name="What is Linux",
                description="The backbone of many cloud environments",
                order=1,
                estimated_time="20 minutes",
                learning_steps=[
                    LearningStep(order=1, text="Watch: What is Linux?", url="https://youtu.be/PwugmcN1hf8"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase0-topic1-check1", text="I understand what Linux is and why it's important for cloud", order=1),
                ],
            ),
            Topic(
                id="phase0-topic2",
                slug="networking",
                name="What is Networking",
                description="How data moves across networks",
                order=2,
                estimated_time="30 minutes",
                learning_steps=[
                    LearningStep(order=1, text="Watch: Computer Networking in 100 Seconds", url="https://youtu.be/3QhU9jd03a0"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase0-topic2-check1", text="I understand basic networking concepts (IP, DNS, ports)", order=1),
                ],
            ),
            Topic(
                id="phase0-topic3",
                slug="programming",
                name="What is Programming",
                description="Automating tasks and managing cloud resources",
                order=3,
                estimated_time="20 minutes",
                learning_steps=[
                    LearningStep(order=1, text="Watch: Programming in 100 Seconds", url="https://youtu.be/ifo76VyrBYo"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase0-topic3-check1", text="I understand what programming is and why it's useful for cloud engineering", order=1),
                ],
            ),
            Topic(
                id="phase0-topic4",
                slug="cloud-computing",
                name="What is Cloud Computing",
                description="IaaS, PaaS, SaaS and service models",
                order=4,
                estimated_time="30 minutes",
                learning_steps=[
                    LearningStep(order=1, text="Watch: Cloud Computing Explained", url="https://youtu.be/eZLcyTxi8ZI"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase0-topic4-check1", text="I understand the cloud service models (IaaS, PaaS, SaaS)", order=1),
                    TopicChecklistItem(id="phase0-topic4-check2", text="I understand the benefits of cloud computing", order=2),
                ],
            ),
            Topic(
                id="phase0-topic5",
                slug="devops",
                name="What is DevOps",
                description="Combining Dev and Ops practices",
                order=5,
                estimated_time="20 minutes",
                learning_steps=[
                    LearningStep(order=1, text="Watch: DevOps Explained", url="https://youtu.be/9pZ2xmsSDdo/"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase0-topic5-check1", text="I understand what DevOps is and its core principles", order=1),
                ],
            ),
            Topic(
                id="phase0-topic6",
                slug="cloud-engineer",
                name="What is a Cloud Engineer",
                description="The role and how to become one",
                order=6,
                estimated_time="25 minutes",
                learning_steps=[
                    LearningStep(order=1, text="Watch: What is a Cloud Engineer?", url="https://youtu.be/7i1WMGxyt4Q"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase0-topic6-check1", text="I understand what cloud engineers do", order=1),
                    TopicChecklistItem(id="phase0-topic6-check2", text="I am committed to pursuing a career in cloud", order=2),
                ],
            ),
        ],
        checklist=[
            ChecklistItem(id="phase0-check1", text="I understand the basics of IT and cloud computing", order=1),
            ChecklistItem(id="phase0-check2", text="I know at a high level what Linux, networking, and programming are", order=2),
            ChecklistItem(id="phase0-check3", text="I understand what cloud engineers do", order=3),
            ChecklistItem(id="phase0-check4", text="I am committed to pursuing a career in tech", order=4),
        ]
    ),
    Phase(
        id=1,
        name="Linux and Bash",
        slug="phase1",
        description="Here at Learn to Cloud, we like to get hands-on as soon as possible. So, we've prepared a Capture The Flag (CTF) lab for you to practice your Linux and Bash. Before you can access them, you'll spend time learning about the lab and setting it up.",
        estimated_weeks="2-3 weeks",
        order=1,
        prerequisites=["Mac OS or Ubuntu based computer (Windows users use WSL)", "Join the Learn to Cloud Discord"],
        topics=[
            Topic(
                id="phase1-topic1",
                slug="version-control",
                name="Version Control",
                description="Git, GitHub, and managing your code",
                order=1,
                estimated_time="3-4 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: Git and GitHub in Plain English", url="https://blog.red-badger.com/2016/11/29/gitgithub-in-plain-english"),
                    LearningStep(order=2, text="Watch: Git Tutorial for Beginners", url="https://youtu.be/8JJ101D3knE?si=6pz2LqE0P9jEPXi5"),
                    LearningStep(order=3, text="Read: How To Use Git", url="https://www.digitalocean.com/community/cheatsheets/how-to-use-git-a-reference-guide"),
                    LearningStep(order=4, text="Read: GitHub Hello World", url="https://docs.github.com/en/get-started/start-your-journey/hello-world"),
                    LearningStep(order=5, text="Complete: Git-it (Electron)", url="https://github.com/jlord/git-it-electron"),
                    LearningStep(order=6, text="Complete: Learn Git Branching", url="https://learngitbranching.js.org/"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase1-topic1-check1", text="I have installed Git", order=1),
                    TopicChecklistItem(id="phase1-topic1-check2", text="I understand the difference between Git and GitHub", order=2),
                    TopicChecklistItem(id="phase1-topic1-check3", text="I have a GitHub account", order=3),
                    TopicChecklistItem(id="phase1-topic1-check4", text="I have forked a repository", order=4),
                    TopicChecklistItem(id="phase1-topic1-check5", text="I have cloned a repository", order=5),
                    TopicChecklistItem(id="phase1-topic1-check6", text="I have pushed changes to a repository", order=6),
                ],
            ),
            Topic(
                id="phase1-topic2",
                slug="cloud-cli",
                name="Cloud CLI",
                description="Command line interfaces for cloud platforms",
                order=2,
                estimated_time="2 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: What is the Cloud CLI?", url="https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-welcome.html"),
                    LearningStep(order=2, text="Install: AWS CLI", url="https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"),
                    LearningStep(order=3, text="Install: Azure CLI", url="https://learn.microsoft.com/en-us/cli/azure/install-azure-cli"),
                    LearningStep(order=4, text="Install: gcloud CLI", url="https://cloud.google.com/sdk/docs/install"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase1-topic2-check1", text="I understand what cloud CLIs are", order=1),
                    TopicChecklistItem(id="phase1-topic2-check2", text="I have installed at least one cloud CLI", order=2),
                    TopicChecklistItem(id="phase1-topic2-check3", text="I can run basic commands with my chosen CLI", order=3),
                ],
            ),
            Topic(
                id="phase1-topic3",
                slug="iac",
                name="Infrastructure as Code",
                description="Introduction to IaC concepts",
                order=3,
                estimated_time="1-2 hours",
                learning_steps=[
                    LearningStep(order=1, text="Watch: What is Infrastructure as Code?", url="https://youtu.be/zWw2wuiKd5o"),
                    LearningStep(order=2, text="Read: Introduction to IaC", url="https://www.redhat.com/en/topics/automation/what-is-infrastructure-as-code-iac"),
                    LearningStep(order=3, text="Read: Terraform Introduction", url="https://developer.hashicorp.com/terraform/intro"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase1-topic3-check1", text="I understand what Infrastructure as Code is", order=1),
                    TopicChecklistItem(id="phase1-topic3-check2", text="I know the benefits of IaC over manual configuration", order=2),
                    TopicChecklistItem(id="phase1-topic3-check3", text="I have heard of tools like Terraform, Pulumi, or CloudFormation", order=3),
                ],
            ),
            Topic(
                id="phase1-topic4",
                slug="ssh",
                name="SSH",
                description="Secure shell and remote access",
                order=4,
                estimated_time="1-2 hours",
                learning_steps=[
                    LearningStep(order=1, text="Watch: SSH Crash Course", url="https://youtu.be/hQWRp-FdTpc"),
                    LearningStep(order=2, text="Read: SSH Key Authentication", url="https://www.ssh.com/academy/ssh/public-key-authentication"),
                    LearningStep(order=3, text="Practice: Generate SSH keys", url="https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase1-topic4-check1", text="I understand what SSH is and why it's used", order=1),
                    TopicChecklistItem(id="phase1-topic4-check2", text="I have generated an SSH key pair", order=2),
                    TopicChecklistItem(id="phase1-topic4-check3", text="I have added my SSH key to GitHub", order=3),
                ],
            ),
            Topic(
                id="phase1-topic5",
                slug="cli-basics",
                name="CLI Basics",
                description="Essential command line skills",
                order=5,
                estimated_time="3-4 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: Command Line Basics", url="https://ubuntu.com/tutorials/command-line-for-beginners"),
                    LearningStep(order=2, text="Practice: Linux Journey", url="https://linuxjourney.com/"),
                    LearningStep(order=3, text="Read: Bash Scripting Guide", url="https://www.freecodecamp.org/news/bash-scripting-tutorial-linux-shell-script-and-command-line-for-beginners/"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase1-topic5-check1", text="I can navigate directories (cd, ls, pwd)", order=1),
                    TopicChecklistItem(id="phase1-topic5-check2", text="I can create, move, and delete files", order=2),
                    TopicChecklistItem(id="phase1-topic5-check3", text="I understand file permissions (chmod, chown)", order=3),
                    TopicChecklistItem(id="phase1-topic5-check4", text="I can use pipes and redirects", order=4),
                    TopicChecklistItem(id="phase1-topic5-check5", text="I can write basic bash scripts", order=5),
                ],
            ),
            Topic(
                id="phase1-topic6",
                slug="ctf-lab",
                name="CTF Lab",
                description="Hands-on Linux challenges",
                order=6,
                estimated_time="4-6 hours",
                is_capstone=True,
                learning_steps=[
                    LearningStep(order=1, text="Read: CTF Lab Setup Guide", url="https://learntocloud.guide/phase1/ctf"),
                    LearningStep(order=2, text="Complete: Learn to Cloud CTF Challenges", url="https://github.com/learntocloud/ltc-linux-challenge"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase1-topic6-check1", text="I have set up the CTF environment", order=1),
                    TopicChecklistItem(id="phase1-topic6-check2", text="I have completed the CTF challenges", order=2),
                ],
            ),
        ],
        checklist=[
            ChecklistItem(id="phase1-check1", text="Git is installed and I understand basic version control", order=1),
            ChecklistItem(id="phase1-check2", text="VS Code is installed and configured", order=2),
            ChecklistItem(id="phase1-check3", text="I can navigate the terminal and use basic commands", order=3),
            ChecklistItem(id="phase1-check4", text="I understand what Infrastructure as Code is", order=4),
            ChecklistItem(id="phase1-check5", text="I completed the CTF challenges", order=5),
            ChecklistItem(id="phase1-check6", text="WSL is set up (Windows users only)", order=6),
        ]
    ),
    Phase(
        id=2,
        name="Programming & AI Integration",
        slug="phase2",
        description="This phase is all about programming with Python and integrating AI capabilities into your applications. Programming is a fundamental skill for cloud engineering, enabling you to create, manage, and optimize cloud resources efficiently.",
        estimated_weeks="4-5 weeks",
        order=2,
        prerequisites=["Completed Phase 1: Linux and Bash", "Completed Phase 1: Linux CTFs"],
        topics=[
            Topic(
                id="phase2-topic1",
                slug="python",
                name="Python",
                description="Programming fundamentals with Python",
                order=1,
                estimated_time="8-10 hours",
                learning_steps=[
                    LearningStep(order=1, text="Complete: Python Basics Tutorial", url="https://www.learnpython.org/"),
                    LearningStep(order=2, text="Read: Python Documentation Tutorial", url="https://docs.python.org/3/tutorial/"),
                    LearningStep(order=3, text="Practice: Codecademy Python", url="https://www.codecademy.com/learn/learn-python-3"),
                    LearningStep(order=4, text="Practice: Python Exercises", url="https://www.practicepython.org/"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase2-topic1-check1", text="I have Python installed on my machine", order=1),
                    TopicChecklistItem(id="phase2-topic1-check2", text="I understand variables, data types, and operators", order=2),
                    TopicChecklistItem(id="phase2-topic1-check3", text="I can write functions and use control flow", order=3),
                    TopicChecklistItem(id="phase2-topic1-check4", text="I understand lists, dictionaries, and loops", order=4),
                    TopicChecklistItem(id="phase2-topic1-check5", text="I can read and write files in Python", order=5),
                ],
            ),
            Topic(
                id="phase2-topic2",
                slug="apis",
                name="APIs",
                description="Understanding REST APIs",
                order=2,
                estimated_time="2-3 hours",
                learning_steps=[
                    LearningStep(order=1, text="Watch: What is an API?", url="https://www.youtube.com/watch?v=s7wmiS2mSXY"),
                    LearningStep(order=2, text="Read: REST API Tutorial", url="https://restfulapi.net/"),
                    LearningStep(order=3, text="Practice: Public APIs List", url="https://github.com/public-apis/public-apis"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase2-topic2-check1", text="I understand what APIs are and how they work", order=1),
                    TopicChecklistItem(id="phase2-topic2-check2", text="I know HTTP methods (GET, POST, PUT, DELETE)", order=2),
                    TopicChecklistItem(id="phase2-topic2-check3", text="I can make API requests using Python or curl", order=3),
                ],
            ),
            Topic(
                id="phase2-topic3",
                slug="fastapi",
                name="FastAPI",
                description="Building APIs with FastAPI",
                order=3,
                estimated_time="4-5 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: FastAPI Documentation", url="https://fastapi.tiangolo.com/tutorial/"),
                    LearningStep(order=2, text="Complete: FastAPI First Steps", url="https://fastapi.tiangolo.com/tutorial/first-steps/"),
                    LearningStep(order=3, text="Build: Create a simple API", url="https://fastapi.tiangolo.com/tutorial/body/"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase2-topic3-check1", text="I have installed FastAPI and Uvicorn", order=1),
                    TopicChecklistItem(id="phase2-topic3-check2", text="I can create basic API endpoints", order=2),
                    TopicChecklistItem(id="phase2-topic3-check3", text="I understand path parameters and query parameters", order=3),
                    TopicChecklistItem(id="phase2-topic3-check4", text="I can handle request bodies with Pydantic", order=4),
                ],
            ),
            Topic(
                id="phase2-topic4",
                slug="databases",
                name="Databases",
                description="Working with databases",
                order=4,
                estimated_time="4-5 hours",
                learning_steps=[
                    LearningStep(order=1, text="Watch: SQL Tutorial", url="https://www.youtube.com/watch?v=HXV3zeQKqGY"),
                    LearningStep(order=2, text="Practice: SQLBolt", url="https://sqlbolt.com/"),
                    LearningStep(order=3, text="Read: PostgreSQL Tutorial", url="https://www.postgresqltutorial.com/"),
                    LearningStep(order=4, text="Read: SQLAlchemy Documentation", url="https://docs.sqlalchemy.org/en/20/tutorial/"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase2-topic4-check1", text="I understand relational database concepts", order=1),
                    TopicChecklistItem(id="phase2-topic4-check2", text="I can write basic SQL queries", order=2),
                    TopicChecklistItem(id="phase2-topic4-check3", text="I can use an ORM like SQLAlchemy", order=3),
                    TopicChecklistItem(id="phase2-topic4-check4", text="I can connect a database to my FastAPI app", order=4),
                ],
            ),
            Topic(
                id="phase2-topic5",
                slug="genai-apis",
                name="GenAI APIs",
                description="Integrating generative AI",
                order=5,
                estimated_time="3-4 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: OpenAI API Quickstart", url="https://platform.openai.com/docs/quickstart"),
                    LearningStep(order=2, text="Read: Azure OpenAI Service", url="https://learn.microsoft.com/en-us/azure/ai-services/openai/overview"),
                    LearningStep(order=3, text="Practice: Build a chat completion", url="https://platform.openai.com/docs/guides/chat-completions"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase2-topic5-check1", text="I have an API key for OpenAI or Azure OpenAI", order=1),
                    TopicChecklistItem(id="phase2-topic5-check2", text="I can make chat completion API calls", order=2),
                    TopicChecklistItem(id="phase2-topic5-check3", text="I understand token limits and pricing", order=3),
                ],
            ),
            Topic(
                id="phase2-topic6",
                slug="prompt-engineering",
                name="Prompt Engineering",
                description="Effective prompting techniques",
                order=6,
                estimated_time="2-3 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: Prompt Engineering Guide", url="https://www.promptingguide.ai/"),
                    LearningStep(order=2, text="Read: OpenAI Best Practices", url="https://platform.openai.com/docs/guides/prompt-engineering"),
                    LearningStep(order=3, text="Practice: Experiment with prompts", url="https://platform.openai.com/playground"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase2-topic6-check1", text="I understand prompt engineering principles", order=1),
                    TopicChecklistItem(id="phase2-topic6-check2", text="I can write effective system prompts", order=2),
                    TopicChecklistItem(id="phase2-topic6-check3", text="I understand few-shot learning", order=3),
                ],
            ),
            Topic(
                id="phase2-topic7",
                slug="build-the-app",
                name="Build the App",
                description="Capstone project",
                order=7,
                estimated_time="6-8 hours",
                is_capstone=True,
                learning_steps=[
                    LearningStep(order=1, text="Build: Create a Journal API with AI features", url="https://learntocloud.guide/phase2/capstone"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase2-topic7-check1", text="I have built a FastAPI backend", order=1),
                    TopicChecklistItem(id="phase2-topic7-check2", text="I have connected a database", order=2),
                    TopicChecklistItem(id="phase2-topic7-check3", text="I have integrated GenAI features", order=3),
                    TopicChecklistItem(id="phase2-topic7-check4", text="My capstone project is complete and working", order=4),
                ],
            ),
        ],
        checklist=[
            ChecklistItem(id="phase2-check1", text="I can write Python scripts and understand core concepts", order=1),
            ChecklistItem(id="phase2-check2", text="I understand how REST APIs work", order=2),
            ChecklistItem(id="phase2-check3", text="I can build a basic API with FastAPI", order=3),
            ChecklistItem(id="phase2-check4", text="I know how to work with databases", order=4),
            ChecklistItem(id="phase2-check5", text="I can integrate GenAI APIs into my applications", order=5),
            ChecklistItem(id="phase2-check6", text="I completed the capstone project", order=6),
        ]
    ),
    Phase(
        id=3,
        name="Cloud Platform Fundamentals",
        slug="phase3",
        description="This phase focuses on cloud platform fundamentals - the core concepts and skills you need to work effectively with cloud services. You'll learn everything from virtual machines and networking to security and application deployment.",
        estimated_weeks="4-5 weeks",
        order=3,
        prerequisites=["Completed Phase 1: Linux and Bash", "Completed Phase 2: Programming & AI Integration", "Git and version control fundamentals", "A cloud platform account (AWS, Azure, or GCP)"],
        topics=[
            Topic(
                id="phase3-topic1",
                slug="vms-compute",
                name="Virtual Machines & Compute",
                description="Learn compute services and VM deployment",
                order=1,
                estimated_time="3-4 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: What is a Virtual Machine?", url="https://azure.microsoft.com/en-us/resources/cloud-computing-dictionary/what-is-a-virtual-machine"),
                    LearningStep(order=2, text="Practice: Launch an EC2 Instance (AWS)", url="https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EC2_GetStarted.html"),
                    LearningStep(order=3, text="Practice: Create a VM (Azure)", url="https://learn.microsoft.com/en-us/azure/virtual-machines/linux/quick-create-portal"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase3-topic1-check1", text="I understand what virtual machines are", order=1),
                    TopicChecklistItem(id="phase3-topic1-check2", text="I can create and configure a VM", order=2),
                    TopicChecklistItem(id="phase3-topic1-check3", text="I can SSH into my VM", order=3),
                ],
            ),
            Topic(
                id="phase3-topic2",
                slug="security-iam",
                name="Security & IAM",
                description="Master identity management and security",
                order=2,
                estimated_time="3-4 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: IAM Introduction (AWS)", url="https://docs.aws.amazon.com/IAM/latest/UserGuide/introduction.html"),
                    LearningStep(order=2, text="Read: Azure RBAC", url="https://learn.microsoft.com/en-us/azure/role-based-access-control/overview"),
                    LearningStep(order=3, text="Practice: Create IAM policies", url="https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_create.html"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase3-topic2-check1", text="I understand IAM concepts (users, roles, policies)", order=1),
                    TopicChecklistItem(id="phase3-topic2-check2", text="I can create and manage IAM users/roles", order=2),
                    TopicChecklistItem(id="phase3-topic2-check3", text="I understand the principle of least privilege", order=3),
                ],
            ),
            Topic(
                id="phase3-topic3",
                slug="cloud-networking",
                name="Cloud Networking",
                description="Configure VPCs, subnets and routing",
                order=3,
                estimated_time="4-5 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: VPC Fundamentals", url="https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html"),
                    LearningStep(order=2, text="Read: Azure Virtual Network", url="https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-overview"),
                    LearningStep(order=3, text="Practice: Create a VPC with subnets", url="https://docs.aws.amazon.com/vpc/latest/userguide/vpc-getting-started.html"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase3-topic3-check1", text="I understand VPCs, subnets, and CIDR blocks", order=1),
                    TopicChecklistItem(id="phase3-topic3-check2", text="I can configure security groups and NACLs", order=2),
                    TopicChecklistItem(id="phase3-topic3-check3", text="I understand routing tables and internet gateways", order=3),
                ],
            ),
            Topic(
                id="phase3-topic4",
                slug="secure-remote-access",
                name="Secure Remote Access",
                description="Set up secure resource access",
                order=4,
                estimated_time="2-3 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: Bastion Hosts", url="https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/access-a-bastion-host-by-using-session-manager.html"),
                    LearningStep(order=2, text="Read: Azure Bastion", url="https://learn.microsoft.com/en-us/azure/bastion/bastion-overview"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase3-topic4-check1", text="I understand bastion hosts and jump boxes", order=1),
                    TopicChecklistItem(id="phase3-topic4-check2", text="I can securely access private resources", order=2),
                ],
            ),
            Topic(
                id="phase3-topic5",
                slug="database-deployment",
                name="Database Deployment",
                description="Deploy and manage databases",
                order=5,
                estimated_time="3-4 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: Amazon RDS", url="https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Welcome.html"),
                    LearningStep(order=2, text="Read: Azure Database for PostgreSQL", url="https://learn.microsoft.com/en-us/azure/postgresql/"),
                    LearningStep(order=3, text="Practice: Deploy a managed database", url="https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_GettingStarted.CreatingConnecting.PostgreSQL.html"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase3-topic5-check1", text="I understand managed database services", order=1),
                    TopicChecklistItem(id="phase3-topic5-check2", text="I can deploy a cloud database", order=2),
                    TopicChecklistItem(id="phase3-topic5-check3", text="I can connect my application to the database", order=3),
                ],
            ),
            Topic(
                id="phase3-topic6",
                slug="fastapi-deployment",
                name="FastAPI Deployment",
                description="Host web applications",
                order=6,
                estimated_time="3-4 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: App Service Overview (Azure)", url="https://learn.microsoft.com/en-us/azure/app-service/overview"),
                    LearningStep(order=2, text="Read: Elastic Beanstalk (AWS)", url="https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/Welcome.html"),
                    LearningStep(order=3, text="Practice: Deploy your FastAPI app", url="https://learntocloud.guide/phase3/deployment"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase3-topic6-check1", text="I understand PaaS deployment options", order=1),
                    TopicChecklistItem(id="phase3-topic6-check2", text="I can deploy my FastAPI application to the cloud", order=2),
                    TopicChecklistItem(id="phase3-topic6-check3", text="My application is accessible via a public URL", order=3),
                ],
            ),
            Topic(
                id="phase3-topic7",
                slug="billing-cost-management",
                name="Billing & Cost Management",
                description="Monitor spending and optimize costs",
                order=7,
                estimated_time="1-2 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: AWS Cost Management", url="https://docs.aws.amazon.com/cost-management/latest/userguide/what-is-costmanagement.html"),
                    LearningStep(order=2, text="Read: Azure Cost Management", url="https://learn.microsoft.com/en-us/azure/cost-management-billing/"),
                    LearningStep(order=3, text="Practice: Set up billing alerts", url="https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/monitor_estimated_charges_with_cloudwatch.html"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase3-topic7-check1", text="I understand cloud pricing models", order=1),
                    TopicChecklistItem(id="phase3-topic7-check2", text="I have set up billing alerts", order=2),
                    TopicChecklistItem(id="phase3-topic7-check3", text="I can view and analyze my cloud spending", order=3),
                ],
            ),
            Topic(
                id="phase3-topic8",
                slug="cloud-ai-services",
                name="Cloud AI Service Platforms",
                description="Explore AI platforms and capabilities",
                order=8,
                estimated_time="2-3 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: Azure AI Services", url="https://learn.microsoft.com/en-us/azure/ai-services/"),
                    LearningStep(order=2, text="Read: AWS AI Services", url="https://aws.amazon.com/machine-learning/ai-services/"),
                    LearningStep(order=3, text="Practice: Try a cloud AI service", url="https://learn.microsoft.com/en-us/azure/ai-services/openai/quickstart"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase3-topic8-check1", text="I understand cloud AI service offerings", order=1),
                    TopicChecklistItem(id="phase3-topic8-check2", text="I have used at least one cloud AI service", order=2),
                ],
            ),
            Topic(
                id="phase3-topic9",
                slug="capstone",
                name="Capstone Project",
                description="Build a complete cloud application",
                order=9,
                estimated_time="6-8 hours",
                is_capstone=True,
                learning_steps=[
                    LearningStep(order=1, text="Build: Deploy Journal API to the cloud", url="https://learntocloud.guide/phase3/capstone"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase3-topic9-check1", text="My API is deployed to a cloud platform", order=1),
                    TopicChecklistItem(id="phase3-topic9-check2", text="My database is deployed and connected", order=2),
                    TopicChecklistItem(id="phase3-topic9-check3", text="I have proper IAM and security configured", order=3),
                    TopicChecklistItem(id="phase3-topic9-check4", text="My application is accessible publicly", order=4),
                ],
            ),
        ],
        checklist=[
            ChecklistItem(id="phase3-check1", text="I can deploy and manage virtual machines", order=1),
            ChecklistItem(id="phase3-check2", text="I understand IAM and security best practices", order=2),
            ChecklistItem(id="phase3-check3", text="I can configure VPCs, subnets, and networking", order=3),
            ChecklistItem(id="phase3-check4", text="I can deploy and manage databases in the cloud", order=4),
            ChecklistItem(id="phase3-check5", text="I can host web applications on cloud platforms", order=5),
            ChecklistItem(id="phase3-check6", text="I understand cloud billing and can monitor costs", order=6),
            ChecklistItem(id="phase3-check7", text="I understand AI service platforms and can deploy models", order=7),
            ChecklistItem(id="phase3-check8", text="I completed the capstone project", order=8),
        ]
    ),
    Phase(
        id=4,
        name="DevOps Fundamentals",
        slug="phase4",
        description="This phase covers DevOps fundamentals - the practices and tools that enable teams to deliver software faster and more reliably. You'll learn containerization, CI/CD pipelines, Infrastructure as Code, and monitoring.",
        estimated_weeks="4-5 weeks",
        order=4,
        prerequisites=["Completed Phase 2: Programming & AI Integration (capstone)", "Completed Phase 3: Cloud Platform Fundamentals (capstone)"],
        topics=[
            Topic(
                id="phase4-topic1",
                slug="containers",
                name="Containers",
                description="Docker and containerization fundamentals",
                order=1,
                estimated_time="4-5 hours",
                learning_steps=[
                    LearningStep(order=1, text="Watch: Docker in 100 Seconds", url="https://www.youtube.com/watch?v=Gjnup-PuquQ"),
                    LearningStep(order=2, text="Read: Docker Getting Started", url="https://docs.docker.com/get-started/"),
                    LearningStep(order=3, text="Practice: Containerize your FastAPI app", url="https://fastapi.tiangolo.com/deployment/docker/"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase4-topic1-check1", text="I have Docker installed", order=1),
                    TopicChecklistItem(id="phase4-topic1-check2", text="I understand images vs containers", order=2),
                    TopicChecklistItem(id="phase4-topic1-check3", text="I can write a Dockerfile", order=3),
                    TopicChecklistItem(id="phase4-topic1-check4", text="I can build and run containers", order=4),
                ],
            ),
            Topic(
                id="phase4-topic2",
                slug="cicd",
                name="CI/CD",
                description="Continuous integration and deployment pipelines",
                order=2,
                estimated_time="4-5 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: What is CI/CD?", url="https://www.redhat.com/en/topics/devops/what-is-ci-cd"),
                    LearningStep(order=2, text="Read: GitHub Actions Documentation", url="https://docs.github.com/en/actions"),
                    LearningStep(order=3, text="Practice: Create a CI/CD pipeline", url="https://docs.github.com/en/actions/quickstart"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase4-topic2-check1", text="I understand CI/CD concepts", order=1),
                    TopicChecklistItem(id="phase4-topic2-check2", text="I can create GitHub Actions workflows", order=2),
                    TopicChecklistItem(id="phase4-topic2-check3", text="I have automated tests in my pipeline", order=3),
                    TopicChecklistItem(id="phase4-topic2-check4", text="I have automated deployments", order=4),
                ],
            ),
            Topic(
                id="phase4-topic3",
                slug="infrastructure-as-code",
                name="Infrastructure as Code",
                description="Terraform and automated provisioning",
                order=3,
                estimated_time="5-6 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: Terraform Introduction", url="https://developer.hashicorp.com/terraform/intro"),
                    LearningStep(order=2, text="Complete: Terraform Getting Started", url="https://developer.hashicorp.com/terraform/tutorials/aws-get-started"),
                    LearningStep(order=3, text="Practice: Deploy infrastructure with Terraform", url="https://developer.hashicorp.com/terraform/tutorials"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase4-topic3-check1", text="I have Terraform installed", order=1),
                    TopicChecklistItem(id="phase4-topic3-check2", text="I understand Terraform HCL syntax", order=2),
                    TopicChecklistItem(id="phase4-topic3-check3", text="I can write Terraform configurations", order=3),
                    TopicChecklistItem(id="phase4-topic3-check4", text="I have deployed resources with Terraform", order=4),
                ],
            ),
            Topic(
                id="phase4-topic4",
                slug="container-orchestration",
                name="Container Orchestration",
                description="Kubernetes basics",
                order=4,
                estimated_time="4-5 hours",
                learning_steps=[
                    LearningStep(order=1, text="Watch: Kubernetes Explained", url="https://www.youtube.com/watch?v=VnvRFRk_51k"),
                    LearningStep(order=2, text="Read: Kubernetes Concepts", url="https://kubernetes.io/docs/concepts/"),
                    LearningStep(order=3, text="Practice: Kubernetes Basics Tutorial", url="https://kubernetes.io/docs/tutorials/kubernetes-basics/"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase4-topic4-check1", text="I understand Kubernetes architecture", order=1),
                    TopicChecklistItem(id="phase4-topic4-check2", text="I know what pods, deployments, and services are", order=2),
                    TopicChecklistItem(id="phase4-topic4-check3", text="I can deploy applications to Kubernetes", order=3),
                ],
            ),
            Topic(
                id="phase4-topic5",
                slug="monitoring-observability",
                name="Monitoring & Observability",
                description="Logging, metrics, and alerting",
                order=5,
                estimated_time="3-4 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: Observability Concepts", url="https://www.splunk.com/en_us/data-insider/what-is-observability.html"),
                    LearningStep(order=2, text="Read: Prometheus & Grafana", url="https://prometheus.io/docs/introduction/overview/"),
                    LearningStep(order=3, text="Practice: Set up monitoring", url="https://grafana.com/docs/grafana/latest/getting-started/"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase4-topic5-check1", text="I understand the three pillars of observability", order=1),
                    TopicChecklistItem(id="phase4-topic5-check2", text="I can set up basic monitoring", order=2),
                    TopicChecklistItem(id="phase4-topic5-check3", text="I can create dashboards and alerts", order=3),
                ],
            ),
            Topic(
                id="phase4-topic6",
                slug="capstone",
                name="Capstone Project",
                description="Complete DevOps implementation",
                order=6,
                estimated_time="6-8 hours",
                is_capstone=True,
                learning_steps=[
                    LearningStep(order=1, text="Build: Full DevOps pipeline for Journal API", url="https://learntocloud.guide/phase4/capstone"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase4-topic6-check1", text="My application is containerized", order=1),
                    TopicChecklistItem(id="phase4-topic6-check2", text="I have a CI/CD pipeline", order=2),
                    TopicChecklistItem(id="phase4-topic6-check3", text="My infrastructure is defined as code", order=3),
                    TopicChecklistItem(id="phase4-topic6-check4", text="I have monitoring and alerting set up", order=4),
                ],
            ),
        ],
        checklist=[
            ChecklistItem(id="phase4-check1", text="I can build and manage Docker containers", order=1),
            ChecklistItem(id="phase4-check2", text="I can set up CI/CD pipelines", order=2),
            ChecklistItem(id="phase4-check3", text="I can write Infrastructure as Code with Terraform", order=3),
            ChecklistItem(id="phase4-check4", text="I understand container orchestration concepts", order=4),
            ChecklistItem(id="phase4-check5", text="I can implement basic monitoring and alerting", order=5),
            ChecklistItem(id="phase4-check6", text="I completed the capstone project", order=6),
        ]
    ),
    Phase(
        id=5,
        name="Securing Your Cloud Applications",
        slug="phase5",
        description="This phase focuses on securing the cloud applications and infrastructure you've built throughout your journey. You'll take the Journal API application from previous phases and implement enterprise-grade security controls, monitoring, and incident response capabilities.",
        estimated_weeks="3-4 weeks",
        order=5,
        prerequisites=["Completed Phase 3: Cloud Platform Fundamentals", "Completed Phase 4: DevOps Fundamentals (recommended)", "Access to the Journal API application", "A cloud platform account with administrative permissions"],
        topics=[
            Topic(
                id="phase5-topic1",
                slug="identity-access-management",
                name="Identity and Access Management",
                description="Secure IAM controls for your Journal API",
                order=1,
                estimated_time="3-4 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: IAM Security Best Practices", url="https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html"),
                    LearningStep(order=2, text="Read: Azure AD Security", url="https://learn.microsoft.com/en-us/azure/security/fundamentals/identity-management-best-practices"),
                    LearningStep(order=3, text="Practice: Implement least privilege access", url="https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase5-topic1-check1", text="I have reviewed and tightened IAM policies", order=1),
                    TopicChecklistItem(id="phase5-topic1-check2", text="I have implemented MFA for admin accounts", order=2),
                    TopicChecklistItem(id="phase5-topic1-check3", text="I follow the principle of least privilege", order=3),
                ],
            ),
            Topic(
                id="phase5-topic2",
                slug="data-protection-secrets",
                name="Data Protection & Secrets",
                description="Encryption, key management, and secure secrets",
                order=2,
                estimated_time="3-4 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: AWS Secrets Manager", url="https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html"),
                    LearningStep(order=2, text="Read: Azure Key Vault", url="https://learn.microsoft.com/en-us/azure/key-vault/general/overview"),
                    LearningStep(order=3, text="Practice: Store and retrieve secrets", url="https://docs.aws.amazon.com/secretsmanager/latest/userguide/tutorials_basic.html"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase5-topic2-check1", text="I have moved secrets out of code", order=1),
                    TopicChecklistItem(id="phase5-topic2-check2", text="I am using a secrets manager", order=2),
                    TopicChecklistItem(id="phase5-topic2-check3", text="My data at rest is encrypted", order=3),
                ],
            ),
            Topic(
                id="phase5-topic3",
                slug="network-security",
                name="Network Security",
                description="Secure networking and connectivity",
                order=3,
                estimated_time="3-4 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: VPC Security Best Practices", url="https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-best-practices.html"),
                    LearningStep(order=2, text="Read: Azure Network Security", url="https://learn.microsoft.com/en-us/azure/security/fundamentals/network-best-practices"),
                    LearningStep(order=3, text="Practice: Configure WAF", url="https://docs.aws.amazon.com/waf/latest/developerguide/getting-started.html"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase5-topic3-check1", text="My security groups follow least privilege", order=1),
                    TopicChecklistItem(id="phase5-topic3-check2", text="I have a WAF configured", order=2),
                    TopicChecklistItem(id="phase5-topic3-check3", text="My VPC is properly segmented", order=3),
                ],
            ),
            Topic(
                id="phase5-topic4",
                slug="security-monitoring",
                name="Security Monitoring",
                description="Real-time monitoring and alerting",
                order=4,
                estimated_time="3-4 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: AWS CloudTrail", url="https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html"),
                    LearningStep(order=2, text="Read: Azure Monitor", url="https://learn.microsoft.com/en-us/azure/azure-monitor/overview"),
                    LearningStep(order=3, text="Practice: Set up security alerts", url="https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_findings.html"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase5-topic4-check1", text="I have audit logging enabled", order=1),
                    TopicChecklistItem(id="phase5-topic4-check2", text="I have security alerts configured", order=2),
                    TopicChecklistItem(id="phase5-topic4-check3", text="I can investigate security events", order=3),
                ],
            ),
            Topic(
                id="phase5-topic5",
                slug="threat-detection-response",
                name="Threat Detection & Response",
                description="Automated threat detection and incident response",
                order=5,
                estimated_time="3-4 hours",
                learning_steps=[
                    LearningStep(order=1, text="Read: AWS GuardDuty", url="https://docs.aws.amazon.com/guardduty/latest/ug/what-is-guardduty.html"),
                    LearningStep(order=2, text="Read: Azure Sentinel", url="https://learn.microsoft.com/en-us/azure/sentinel/overview"),
                    LearningStep(order=3, text="Practice: Create incident response runbooks", url="https://docs.aws.amazon.com/incident-manager/latest/userguide/what-is-incident-manager.html"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase5-topic5-check1", text="I have threat detection enabled", order=1),
                    TopicChecklistItem(id="phase5-topic5-check2", text="I have an incident response plan", order=2),
                    TopicChecklistItem(id="phase5-topic5-check3", text="I can respond to security incidents", order=3),
                ],
            ),
            Topic(
                id="phase5-topic6",
                slug="capstone",
                name="Capstone Project",
                description="Comprehensive security implementation",
                order=6,
                estimated_time="6-8 hours",
                is_capstone=True,
                learning_steps=[
                    LearningStep(order=1, text="Build: Secure the Journal API end-to-end", url="https://learntocloud.guide/phase5/capstone"),
                ],
                checklist=[
                    TopicChecklistItem(id="phase5-topic6-check1", text="IAM is properly configured", order=1),
                    TopicChecklistItem(id="phase5-topic6-check2", text="Secrets are managed securely", order=2),
                    TopicChecklistItem(id="phase5-topic6-check3", text="Network security is implemented", order=3),
                    TopicChecklistItem(id="phase5-topic6-check4", text="Security monitoring is active", order=4),
                    TopicChecklistItem(id="phase5-topic6-check5", text="Threat detection and response is in place", order=5),
                ],
            ),
        ],
        checklist=[
            ChecklistItem(id="phase5-check1", text="I implemented proper IAM controls and least-privilege access", order=1),
            ChecklistItem(id="phase5-check2", text="I configured encryption and secrets management", order=2),
            ChecklistItem(id="phase5-check3", text="I set up network security and secure connectivity", order=3),
            ChecklistItem(id="phase5-check4", text="I implemented security monitoring and alerting", order=4),
            ChecklistItem(id="phase5-check5", text="I can detect and respond to security incidents", order=5),
            ChecklistItem(id="phase5-check6", text="I completed the capstone project", order=6),
        ]
    ),
]


def get_all_phases() -> list[Phase]:
    """Get all phases."""
    return PHASES


def get_phase_by_id(phase_id: int) -> Phase | None:
    """Get a phase by ID."""
    for phase in PHASES:
        if phase.id == phase_id:
            return phase
    return None


def get_phase_by_slug(slug: str) -> Phase | None:
    """Get a phase by slug."""
    for phase in PHASES:
        if phase.slug == slug:
            return phase
    return None


def get_topic_by_slug(phase_slug: str, topic_slug: str) -> Topic | None:
    """Get a topic by phase slug and topic slug."""
    phase = get_phase_by_slug(phase_slug)
    if not phase:
        return None
    for topic in phase.topics:
        if topic.slug == topic_slug:
            return topic
    return None


def get_total_topics() -> int:
    """Get total number of topics across all phases."""
    return sum(len(phase.topics) for phase in PHASES)


def get_total_checklist_items() -> int:
    """Get total number of checklist items (phase + topic level) across all phases."""
    total = sum(len(phase.checklist) for phase in PHASES)
    for phase in PHASES:
        total += sum(len(topic.checklist) for topic in phase.topics)
    return total


def get_all_checklist_item_ids() -> list[str]:
    """Get all checklist item IDs (phase + topic level)."""
    ids = []
    for phase in PHASES:
        for item in phase.checklist:
            ids.append(item.id)
        for topic in phase.topics:
            for item in topic.checklist:
                ids.append(item.id)
    return ids
