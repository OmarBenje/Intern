-- Intern DEV 1 / étape 3. Généré depuis les migrations et seed_dev.
-- Base dédiée uniquement ; voir donnees/README.md.
BEGIN;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM auth_user) OR EXISTS (SELECT 1 FROM jobboard_company) THEN
    RAISE EXCEPTION 'Peuplement refusé : base déjà utilisée';
  END IF;
END $$;
SET CONSTRAINTS ALL DEFERRED;
--
-- PostgreSQL database dump
--

\restrict jekPf1zrgdpzc90EbwNjbj00NRUCdNbcws0rVDdliBMGIKyzNjf4Wyeq7JaKvvL

-- Dumped from database version 16.10 (Debian 16.10-1.pgdg13+1)
-- Dumped by pg_dump version 16.13

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET LOCAL search_path = public, pg_catalog;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: auth_group; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.auth_group (id, name) FROM stdin;
\.


--
-- Data for Name: django_content_type; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.django_content_type (id, app_label, model) FROM stdin;
1	admin	logentry
2	auth	group
3	auth	permission
4	auth	user
5	contenttypes	contenttype
6	sessions	session
7	jobboard	agentrun
8	jobboard	alertevent
9	jobboard	application
10	jobboard	applicationevent
11	jobboard	applicationrevision
12	jobboard	applicationtask
13	jobboard	atsprobe
14	jobboard	boardschedule
15	jobboard	candidateprofile
16	jobboard	candidateskill
17	jobboard	company
18	jobboard	companypreference
19	jobboard	companyprofile
20	jobboard	compensationband
21	jobboard	deletionrequest
22	jobboard	discoveryquery
23	jobboard	discoveryresult
24	jobboard	document
25	jobboard	education
26	jobboard	experience
27	jobboard	externalopportunity
28	jobboard	importrun
29	jobboard	interview
30	jobboard	jobdomain
31	jobboard	jobsubdomain
32	jobboard	location
33	jobboard	offer
34	jobboard	offerenrichment
35	jobboard	offerfeedback
36	jobboard	offerlocation
37	jobboard	offermergedecision
38	jobboard	offerreport
39	jobboard	offerskill
40	jobboard	offersource
41	jobboard	outboxmessage
42	jobboard	preferencecontract
43	jobboard	preferencelocation
44	jobboard	preferencerole
45	jobboard	preferenceworkmode
46	jobboard	project
47	jobboard	recruiterapplicant
48	jobboard	recruiterintegration
49	jobboard	recruiterjob
50	jobboard	recruiterprofile
51	jobboard	requestthrottle
52	jobboard	revisiondocument
53	jobboard	role
54	jobboard	savedoffer
55	jobboard	savedsearch
56	jobboard	searchpreference
57	jobboard	skill
58	jobboard	sourceboard
59	jobboard	sourcecandidate
60	jobboard	sourcediscoveryseed
61	jobboard	sourceobservation
62	jobboard	sourcerevision
63	jobboard	submissionauthorization
64	jobboard	workauthorization
\.


--
-- Data for Name: auth_permission; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.auth_permission (id, name, content_type_id, codename) FROM stdin;
1	Can add log entry	1	add_logentry
2	Can change log entry	1	change_logentry
3	Can delete log entry	1	delete_logentry
4	Can view log entry	1	view_logentry
5	Can add permission	3	add_permission
6	Can change permission	3	change_permission
7	Can delete permission	3	delete_permission
8	Can view permission	3	view_permission
9	Can add group	2	add_group
10	Can change group	2	change_group
11	Can delete group	2	delete_group
12	Can view group	2	view_group
13	Can add user	4	add_user
14	Can change user	4	change_user
15	Can delete user	4	delete_user
16	Can view user	4	view_user
17	Can add content type	5	add_contenttype
18	Can change content type	5	change_contenttype
19	Can delete content type	5	delete_contenttype
20	Can view content type	5	view_contenttype
21	Can add session	6	add_session
22	Can change session	6	change_session
23	Can delete session	6	delete_session
24	Can view session	6	view_session
25	Can add offer	33	add_offer
26	Can change offer	33	change_offer
27	Can delete offer	33	delete_offer
28	Can view offer	33	view_offer
29	Can add skill	57	add_skill
30	Can change skill	57	change_skill
31	Can delete skill	57	delete_skill
32	Can view skill	57	view_skill
33	Can add candidate profile	15	add_candidateprofile
34	Can change candidate profile	15	change_candidateprofile
35	Can delete candidate profile	15	delete_candidateprofile
36	Can view candidate profile	15	view_candidateprofile
37	Can add location	32	add_location
38	Can change location	32	change_location
39	Can delete location	32	delete_location
40	Can view location	32	view_location
41	Can add role	53	add_role
42	Can change role	53	change_role
43	Can delete role	53	delete_role
44	Can view role	53	view_role
45	Can add search preference	56	add_searchpreference
46	Can change search preference	56	change_searchpreference
47	Can delete search preference	56	delete_searchpreference
48	Can view search preference	56	view_searchpreference
49	Can add company	17	add_company
50	Can change company	17	change_company
51	Can delete company	17	delete_company
52	Can view company	17	view_company
53	Can add offer location	36	add_offerlocation
54	Can change offer location	36	change_offerlocation
55	Can delete offer location	36	delete_offerlocation
56	Can view offer location	36	view_offerlocation
57	Can add offer skill	39	add_offerskill
58	Can change offer skill	39	change_offerskill
59	Can delete offer skill	39	delete_offerskill
60	Can view offer skill	39	view_offerskill
61	Can add compensation band	20	add_compensationband
62	Can change compensation band	20	change_compensationband
63	Can delete compensation band	20	delete_compensationband
64	Can view compensation band	20	view_compensationband
65	Can add import run	28	add_importrun
66	Can change import run	28	change_importrun
67	Can delete import run	28	delete_importrun
68	Can view import run	28	view_importrun
69	Can add offer source	40	add_offersource
70	Can change offer source	40	change_offersource
71	Can delete offer source	40	delete_offersource
72	Can view offer source	40	view_offersource
73	Can add saved offer	54	add_savedoffer
74	Can change saved offer	54	change_savedoffer
75	Can delete saved offer	54	delete_savedoffer
76	Can view saved offer	54	view_savedoffer
77	Can add source board	58	add_sourceboard
78	Can change source board	58	change_sourceboard
79	Can delete source board	58	delete_sourceboard
80	Can view source board	58	view_sourceboard
81	Can add preference location	43	add_preferencelocation
82	Can change preference location	43	change_preferencelocation
83	Can delete preference location	43	delete_preferencelocation
84	Can view preference location	43	view_preferencelocation
85	Can add preference role	44	add_preferencerole
86	Can change preference role	44	change_preferencerole
87	Can delete preference role	44	delete_preferencerole
88	Can view preference role	44	view_preferencerole
89	Can add candidate skill	16	add_candidateskill
90	Can change candidate skill	16	change_candidateskill
91	Can delete candidate skill	16	delete_candidateskill
92	Can view candidate skill	16	view_candidateskill
93	Can add education	25	add_education
94	Can change education	25	change_education
95	Can delete education	25	delete_education
96	Can view education	25	view_education
97	Can add experience	26	add_experience
98	Can change experience	26	change_experience
99	Can delete experience	26	delete_experience
100	Can view experience	26	view_experience
101	Can add preference contract	42	add_preferencecontract
102	Can change preference contract	42	change_preferencecontract
103	Can delete preference contract	42	delete_preferencecontract
104	Can view preference contract	42	view_preferencecontract
105	Can add preference work mode	45	add_preferenceworkmode
106	Can change preference work mode	45	change_preferenceworkmode
107	Can delete preference work mode	45	delete_preferenceworkmode
108	Can view preference work mode	45	view_preferenceworkmode
109	Can add project	46	add_project
110	Can change project	46	change_project
111	Can delete project	46	delete_project
112	Can view project	46	view_project
113	Can add work authorization	64	add_workauthorization
114	Can change work authorization	64	change_workauthorization
115	Can delete work authorization	64	delete_workauthorization
116	Can view work authorization	64	view_workauthorization
117	Can add document	24	add_document
118	Can change document	24	change_document
119	Can delete document	24	delete_document
120	Can view document	24	view_document
121	Can add application	9	add_application
122	Can change application	9	change_application
123	Can delete application	9	delete_application
124	Can view application	9	view_application
125	Can add agent run	7	add_agentrun
126	Can change agent run	7	change_agentrun
127	Can delete agent run	7	delete_agentrun
128	Can view agent run	7	view_agentrun
129	Can add application event	10	add_applicationevent
130	Can change application event	10	change_applicationevent
131	Can delete application event	10	delete_applicationevent
132	Can view application event	10	view_applicationevent
133	Can add application revision	11	add_applicationrevision
134	Can change application revision	11	change_applicationrevision
135	Can delete application revision	11	delete_applicationrevision
136	Can view application revision	11	view_applicationrevision
137	Can add application task	12	add_applicationtask
138	Can change application task	12	change_applicationtask
139	Can delete application task	12	delete_applicationtask
140	Can view application task	12	view_applicationtask
141	Can add deletion request	21	add_deletionrequest
142	Can change deletion request	21	change_deletionrequest
143	Can delete deletion request	21	delete_deletionrequest
144	Can view deletion request	21	view_deletionrequest
145	Can add interview	29	add_interview
146	Can change interview	29	change_interview
147	Can delete interview	29	delete_interview
148	Can view interview	29	view_interview
149	Can add outbox message	41	add_outboxmessage
150	Can change outbox message	41	change_outboxmessage
151	Can delete outbox message	41	delete_outboxmessage
152	Can view outbox message	41	view_outboxmessage
153	Can add revision document	52	add_revisiondocument
154	Can change revision document	52	change_revisiondocument
155	Can delete revision document	52	delete_revisiondocument
156	Can view revision document	52	view_revisiondocument
157	Can add submission authorization	63	add_submissionauthorization
158	Can change submission authorization	63	change_submissionauthorization
159	Can delete submission authorization	63	delete_submissionauthorization
160	Can view submission authorization	63	view_submissionauthorization
161	Can add request throttle	51	add_requestthrottle
162	Can change request throttle	51	change_requestthrottle
163	Can delete request throttle	51	delete_requestthrottle
164	Can view request throttle	51	view_requestthrottle
165	Can add external opportunity	27	add_externalopportunity
166	Can change external opportunity	27	change_externalopportunity
167	Can delete external opportunity	27	delete_externalopportunity
168	Can view external opportunity	27	view_externalopportunity
169	Can add offer report	38	add_offerreport
170	Can change offer report	38	change_offerreport
171	Can delete offer report	38	delete_offerreport
172	Can view offer report	38	view_offerreport
173	Can add source candidate	59	add_sourcecandidate
174	Can change source candidate	59	change_sourcecandidate
175	Can delete source candidate	59	delete_sourcecandidate
176	Can view source candidate	59	view_sourcecandidate
177	Can add source observation	61	add_sourceobservation
178	Can change source observation	61	change_sourceobservation
179	Can delete source observation	61	delete_sourceobservation
180	Can view source observation	61	view_sourceobservation
181	Can add alert event	8	add_alertevent
182	Can change alert event	8	change_alertevent
183	Can delete alert event	8	delete_alertevent
184	Can view alert event	8	view_alertevent
185	Can add board schedule	14	add_boardschedule
186	Can change board schedule	14	change_boardschedule
187	Can delete board schedule	14	delete_boardschedule
188	Can view board schedule	14	view_boardschedule
189	Can add company preference	18	add_companypreference
190	Can change company preference	18	change_companypreference
191	Can delete company preference	18	delete_companypreference
192	Can view company preference	18	view_companypreference
193	Can add offer enrichment	34	add_offerenrichment
194	Can change offer enrichment	34	change_offerenrichment
195	Can delete offer enrichment	34	delete_offerenrichment
196	Can view offer enrichment	34	view_offerenrichment
197	Can add offer feedback	35	add_offerfeedback
198	Can change offer feedback	35	change_offerfeedback
199	Can delete offer feedback	35	delete_offerfeedback
200	Can view offer feedback	35	view_offerfeedback
201	Can add saved search	55	add_savedsearch
202	Can change saved search	55	change_savedsearch
203	Can delete saved search	55	delete_savedsearch
204	Can view saved search	55	view_savedsearch
205	Can add source revision	62	add_sourcerevision
206	Can change source revision	62	change_sourcerevision
207	Can delete source revision	62	delete_sourcerevision
208	Can view source revision	62	view_sourcerevision
209	Can add offer merge decision	37	add_offermergedecision
210	Can change offer merge decision	37	change_offermergedecision
211	Can delete offer merge decision	37	delete_offermergedecision
212	Can view offer merge decision	37	view_offermergedecision
213	Can add source discovery seed	60	add_sourcediscoveryseed
214	Can change source discovery seed	60	change_sourcediscoveryseed
215	Can delete source discovery seed	60	delete_sourcediscoveryseed
216	Can view source discovery seed	60	view_sourcediscoveryseed
217	Can add discovery query	22	add_discoveryquery
218	Can change discovery query	22	change_discoveryquery
219	Can delete discovery query	22	delete_discoveryquery
220	Can view discovery query	22	view_discoveryquery
221	Can add discovery result	23	add_discoveryresult
222	Can change discovery result	23	change_discoveryresult
223	Can delete discovery result	23	delete_discoveryresult
224	Can view discovery result	23	view_discoveryresult
225	Can add ats probe	13	add_atsprobe
226	Can change ats probe	13	change_atsprobe
227	Can delete ats probe	13	delete_atsprobe
228	Can view ats probe	13	view_atsprobe
229	Can add job domain	30	add_jobdomain
230	Can change job domain	30	change_jobdomain
231	Can delete job domain	30	delete_jobdomain
232	Can view job domain	30	view_jobdomain
233	Can add job subdomain	31	add_jobsubdomain
234	Can change job subdomain	31	change_jobsubdomain
235	Can delete job subdomain	31	delete_jobsubdomain
236	Can view job subdomain	31	view_jobsubdomain
237	Can add company profile	19	add_companyprofile
238	Can change company profile	19	change_companyprofile
239	Can delete company profile	19	delete_companyprofile
240	Can view company profile	19	view_companyprofile
241	Can add recruiter job	49	add_recruiterjob
242	Can change recruiter job	49	change_recruiterjob
243	Can delete recruiter job	49	delete_recruiterjob
244	Can view recruiter job	49	view_recruiterjob
245	Can add recruiter applicant	47	add_recruiterapplicant
246	Can change recruiter applicant	47	change_recruiterapplicant
247	Can delete recruiter applicant	47	delete_recruiterapplicant
248	Can view recruiter applicant	47	view_recruiterapplicant
249	Can add recruiter profile	50	add_recruiterprofile
250	Can change recruiter profile	50	change_recruiterprofile
251	Can delete recruiter profile	50	delete_recruiterprofile
252	Can view recruiter profile	50	view_recruiterprofile
253	Can add recruiter integration	48	add_recruiterintegration
254	Can change recruiter integration	48	change_recruiterintegration
255	Can delete recruiter integration	48	delete_recruiterintegration
256	Can view recruiter integration	48	view_recruiterintegration
\.


--
-- Data for Name: auth_group_permissions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.auth_group_permissions (id, group_id, permission_id) FROM stdin;
\.


--
-- Data for Name: auth_user; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.auth_user (id, password, last_login, is_superuser, username, first_name, last_name, email, is_staff, is_active, date_joined) FROM stdin;
1	scrypt$16384$Jsg4DfYC67ZmdRhZD5Ootz$8$5$K4E6+gxc2Dcecrf0GaUz0YO5XiVPHHhsi7KAu+gcPFSxcfBZzF2Whmp1iWoSr8F89cHQGmmHO6IqQruDzBr6Bw==	\N	f	alice			alice@example.test	f	t	2026-10-11 15:05:11.095933+02
2	scrypt$16384$Vp2SUaWbLRWEmAbhRGIRnw$8$5$XbifjrffllxuRdZP4F4xd9urmjc0FS6RZXADZzCZi97WK1plGosxZ271rTa9yRrsbKSuVPy24yc5ouzvd1dkXQ==	\N	f	bob			bob@example.test	f	t	2026-10-11 15:05:11.480957+02
3	scrypt$16384$JsBkSfkeYpChRbsnVWzFjQ$8$5$ywwt6Yn2C6eUWi1uegTA5S4Ac0TqLLCXU7PRwKZBXpwd1Bcl1xpURQJppBolN7OPkWeh0RrTbRuhMQ0jc4Qm5w==	\N	f	vide			vide@example.test	f	t	2026-10-11 15:05:11.851877+02
4	scrypt$16384$7g5xBA3v2gHxipbZ6y18oS$8$5$iwBD7fWgJmtUubUi3CG684dx2qC0zzfy0JLFonDYmHlgqE/ESZFV+cT60A427NZuNu1nkmFBofWsAEQPm/lg1g==	\N	f	attente			attente@example.test	f	f	2026-10-11 15:05:12.250489+02
5	scrypt$16384$5TIxN8xALn1NLwPClxtx9A$8$5$/AtvFeM1loU392hwWibVB6dDdbmdXA4uwFzQy1AzXYHy9CMnl58YNkjxX3CbSPmRbSO/eTQT0w/hZ0T5CX+59w==	\N	t	admin			admin@example.test	t	t	2026-10-11 15:05:12.722162+02
6	scrypt$16384$febnpjEfreQ2PdhtIjFeXr$8$5$mXcojzD5K1GVcfrCVFhCVH7nQ+/1mja7vCSSh1Ar7zky8DAnc+RRajdBrypl5KG8bQ8cq7AgSFM5L1MuACJ31A==	\N	f	recruteur_a			recruteur_a@example.test	f	t	2026-10-11 15:05:13.130507+02
7	scrypt$16384$KLNkHjgooxgJiOlC7zP7NS$8$5$sGzglp4QrnIAqt/Ip9Kl3fzjyrVr035Aeig4XgrkO68m2fMSukkPZvxzakEJ6s8sjPlk7qsGheHR75uHTxUCKg==	\N	f	recruteur_b			recruteur_b@example.test	f	t	2026-10-11 15:05:13.450683+02
8	scrypt$16384$JWaPdGPj2BTi1KzTSL4b44$8$5$ZCrRrBKbTeKI9PNMmawUcdmMjJEM7fCLrCjW9gFHf41/86x5e3f3lt9EGkSZb8hY8qNqnDBTPhFXRh72pVc6pg==	\N	f	recruteur_non_verifie			recruteur_non_verifie@example.test	f	t	2026-10-11 15:05:13.769938+02
\.


--
-- Data for Name: auth_user_groups; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.auth_user_groups (id, user_id, group_id) FROM stdin;
\.


--
-- Data for Name: auth_user_user_permissions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.auth_user_user_permissions (id, user_id, permission_id) FROM stdin;
\.


--
-- Data for Name: django_admin_log; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.django_admin_log (id, action_time, object_id, object_repr, action_flag, change_message, content_type_id, user_id) FROM stdin;
\.


--
-- Data for Name: django_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.django_migrations (id, app, name, applied) FROM stdin;
1	contenttypes	0001_initial	2026-10-11 15:04:57.908405+02
2	auth	0001_initial	2026-10-11 15:04:57.950338+02
3	admin	0001_initial	2026-10-11 15:04:57.96524+02
4	admin	0002_logentry_remove_auto_add	2026-10-11 15:04:57.975034+02
5	admin	0003_logentry_add_action_flag_choices	2026-10-11 15:04:57.985273+02
6	contenttypes	0002_remove_content_type_name	2026-10-11 15:04:58.016616+02
7	auth	0002_alter_permission_name_max_length	2026-10-11 15:04:58.03401+02
8	auth	0003_alter_user_email_max_length	2026-10-11 15:04:58.050203+02
9	auth	0004_alter_user_username_opts	2026-10-11 15:04:58.065536+02
10	auth	0005_alter_user_last_login_null	2026-10-11 15:04:58.082232+02
11	auth	0006_require_contenttypes_0002	2026-10-11 15:04:58.085679+02
12	auth	0007_alter_validators_add_error_messages	2026-10-11 15:04:58.100149+02
13	auth	0008_alter_user_username_max_length	2026-10-11 15:04:58.128619+02
14	auth	0009_alter_user_last_name_max_length	2026-10-11 15:04:58.142013+02
15	auth	0010_alter_group_name_max_length	2026-10-11 15:04:58.158036+02
16	auth	0011_update_proxy_permissions	2026-10-11 15:04:58.173688+02
17	auth	0012_alter_user_first_name_max_length	2026-10-11 15:04:58.189264+02
18	jobboard	0001_initial	2026-10-11 15:04:58.203231+02
19	jobboard	0002_skill_candidateprofile	2026-10-11 15:04:58.2482+02
20	jobboard	0003_location_role_searchpreference	2026-10-11 15:04:58.321333+02
21	jobboard	0004_company_offer_location_offer_role_offer_skills_and_more	2026-10-11 15:04:58.427391+02
22	jobboard	0005_alter_offer_role	2026-10-11 15:04:58.458031+02
23	jobboard	0006_rename_location_offer_locations_offer_contract_type_and_more	2026-10-11 15:04:58.551766+02
24	jobboard	0007_alter_offer_contract_type_alter_offer_work_mode	2026-10-11 15:04:58.600435+02
25	jobboard	0008_alter_offer_contract_type_alter_offer_work_mode	2026-10-11 15:04:58.633519+02
26	jobboard	0009_catalogue	2026-10-11 15:05:00.161026+02
27	jobboard	0010_profile_location_text	2026-10-11 15:05:00.179839+02
28	jobboard	0011_profiles_documents	2026-10-11 15:05:01.770353+02
29	jobboard	0012_applications_operations	2026-10-11 15:05:03.718307+02
30	jobboard	0013_finalize_catalogue_preferences	2026-10-11 15:05:04.377388+02
31	jobboard	0014_composite_foreign_keys	2026-10-11 15:05:04.41125+02
32	jobboard	0015_request_throttle	2026-10-11 15:05:04.418257+02
33	jobboard	0016_candidate_onboarding	2026-10-11 15:05:04.808007+02
34	jobboard	0017_internship_engine	2026-10-11 15:05:05.600099+02
35	jobboard	0018_enrichment_event	2026-10-11 15:05:05.630558+02
36	jobboard	0019_offer_merge_decision	2026-10-11 15:05:05.703715+02
37	jobboard	0020_source_discovery_seed	2026-10-11 15:05:05.711217+02
38	jobboard	0021_coverage_discovery	2026-10-11 15:05:05.806916+02
39	jobboard	0022_company_logo_queue	2026-10-11 15:05:05.840633+02
40	jobboard	0023_discovery_auto_activate	2026-10-11 15:05:05.861882+02
41	jobboard	0024_offer_content	2026-10-11 15:05:05.909676+02
42	jobboard	0025_search_document	2026-10-11 15:05:06.054341+02
43	jobboard	0026_company_logo_provenance	2026-10-11 15:05:06.153511+02
44	jobboard	0027_ats_probe_queue	2026-10-11 15:05:06.229656+02
45	jobboard	0028_job_taxonomy	2026-10-11 15:05:08.192002+02
46	jobboard	0029_company_profiles	2026-10-11 15:05:08.262346+02
47	jobboard	0030_collection_checkpoint	2026-10-11 15:05:08.278578+02
48	jobboard	0031_recruiter_workspace	2026-10-11 15:05:08.669517+02
49	jobboard	0032_recruiter_company_memberships	2026-10-11 15:05:08.757168+02
50	jobboard	0033_password_hash_sql_name	2026-10-11 15:05:08.76179+02
51	jobboard	0034_recruiter_applicant_integrity	2026-10-11 15:05:09.320674+02
52	sessions	0001_initial	2026-10-11 15:05:09.327198+02
\.


--
-- Data for Name: django_session; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.django_session (session_key, session_data, expire_date) FROM stdin;
\.


--
-- Data for Name: jobboard_company; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_company (id, name, created_at, description, domain, logo_object_key, updated_at, website_url, logo_attempts, logo_next_attempt_at, logo_last_error, logo_source_url, logo_source_kind, logo_fetched_at) FROM stdin;
1	Atelier Démo	2026-10-11 15:05:13.126212+02	Entreprise fictive du jeu d'essai DEV.	\N	\N	2026-10-11 15:05:13.126639+02	\N	0	\N				\N
2	Laboratoire Exemple	2026-10-11 15:05:13.128134+02	Entreprise fictive du jeu d'essai DEV.	\N	\N	2026-10-11 15:05:13.12844+02	\N	0	\N				\N
3	Entreprise Sans Offre	2026-10-11 15:05:13.12931+02	Entreprise fictive du jeu d'essai DEV.	\N	\N	2026-10-11 15:05:13.129599+02	\N	0	\N				\N
\.


--
-- Data for Name: jobboard_sourceboard; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_sourceboard (id, provider, instance, board_key, base_url, enabled, submission_mode, adapter_version, last_success_at, company_id) FROM stdin;
1	intern	local	1	https://example.test	t	unsupported	\N	\N	1
2	intern	local	2	https://example.test	t	unsupported	\N	\N	1
3	demo	local	dev-2	https://example.test	t	unsupported	\N	\N	2
\.


--
-- Data for Name: jobboard_importrun; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_importrun (id, status, started_at, finished_at, is_full_snapshot, seen_count, error_code, board_id, diagnostics) FROM stdin;
\.


--
-- Data for Name: jobboard_jobdomain; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_jobdomain (id, slug, name, "position") FROM stdin;
1	software-it	Informatique et systèmes	0
2	data-ai	Data, IA et statistiques	1
3	cybersecurity	Cybersécurité	2
4	engineering	Ingénierie et conception technique	3
5	industrial-operations	Production, qualité et maintenance	4
6	construction	Construction, architecture et urbanisme	5
7	energy-environment	Énergie et environnement	6
8	science-research	Sciences et recherche	7
9	health	Santé et recherche clinique	8
10	finance	Finance, banque et assurance	9
11	accounting-audit	Comptabilité, audit et contrôle	10
12	legal-compliance	Droit et conformité	11
13	consulting-strategy	Conseil, stratégie et organisation	12
14	product-project	Produit et gestion de projet	13
15	marketing	Marketing et acquisition	14
16	communication-media	Communication, médias et rédaction	15
17	sales-customer	Commerce et relation client	16
18	human-resources	Ressources humaines	17
19	supply-chain	Achats, logistique et transport	18
20	design-creative	Design, création et audiovisuel	19
21	agriculture-food	Agriculture, alimentation et animal	20
22	hospitality-tourism	Hôtellerie, restauration et tourisme	21
23	education-social-public	Éducation, social et action publique	22
24	administration-real-estate	Administration, gestion et immobilier	23
\.


--
-- Data for Name: jobboard_jobsubdomain; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_jobsubdomain (id, slug, name, aliases, generalist, "position", domain_id) FROM stdin;
1	frontend	Frontend	["Frontend", "front end", "front-end", "frontend developer", "frontend engineer", "développeur frontend", "frontendentwickler"]	f	0	1
2	backend	Backend	["Backend", "back end", "back-end", "backend developer", "backend engineer", "développement serveur", "backendentwickler"]	f	1	1
3	full-stack	Full stack	["Full stack", "fullstack", "full-stack", "full stack developer"]	f	2	1
4	mobile	Mobile	["Mobile", "mobile developer", "mobile engineer", "android developer", "ios developer", "développeur mobile"]	f	3	1
5	software-generalist	Développement logiciel généraliste	["Développement logiciel généraliste", "software engineer", "software engineering", "software developer", "software development", "développeur logiciel", "développement logiciel", "softwareentwickler", "softwareentwicklung", "développeur", "développeuse", "software engineering internship", "informatique", "it intern", "software", "software intern", "développement informatique"]	t	4	1
6	embedded-software	Systèmes embarqués et firmware	["Systèmes embarqués et firmware", "embedded software", "embedded systems", "firmware", "logiciel embarqué", "systèmes embarqués"]	f	5	1
7	game-development	Jeux vidéo et moteurs graphiques	["Jeux vidéo et moteurs graphiques", "game developer", "game development", "gameplay", "graphics programmer"]	f	6	1
8	software-testing	QA et automatisation des tests	["QA et automatisation des tests", "software testing", "qa engineer", "test automation", "software quality", "quality assurance engineer", "automatisation des tests"]	f	7	1
9	devops-sre	DevOps et SRE	["DevOps et SRE", "devops", "site reliability", "sre", "devsecops"]	f	8	1
10	cloud-platform	Cloud et plateforme	["Cloud et plateforme", "cloud engineer", "platform engineer", "cloud engineering", "cloud architecture"]	f	9	1
11	systems-networks	Systèmes et réseaux	["Systèmes et réseaux", "system administrator", "network engineer", "administrateur système", "réseaux informatiques", "it infrastructure"]	f	10	1
12	it-support	Support et services informatiques	["Support et services informatiques", "it support", "technical support", "support informatique", "service desk"]	f	11	1
13	analytics	Analyse de données	["Analyse de données", "data analyst", "data analytics", "analyste de données", "datenanalyse", "analista de datos", "analista dati"]	f	0	2
14	business-intelligence	Business intelligence	["Business intelligence", "business intelligence", "bi analyst", "business-intelligence"]	f	1	2
15	data-engineering	Data engineering	["Data engineering", "data engineer", "data engineering", "ingénieur données", "data pipelines"]	f	2	2
16	data-science	Data science	["Data science", "data scientist", "data science", "data-science"]	f	3	2
17	machine-learning	Machine learning	["Machine learning", "machine learning", "apprentissage automatique", "deep learning"]	f	4	2
18	generative-ai-nlp	IA générative et NLP	["IA générative et NLP", "generative ai", "natural language processing", "nlp", "large language model", "llm engineer", "ia générative"]	f	5	2
19	computer-vision	Vision par ordinateur	["Vision par ordinateur", "computer vision", "vision par ordinateur", "image recognition", "traitement d'images"]	f	6	2
20	mlops	MLOps	["MLOps", "mlops", "ml ops"]	f	7	2
21	statistics	Statistiques et biostatistiques	["Statistiques et biostatistiques", "statistician", "statistics", "biostatistics", "statistiques", "biostatistiques"]	f	8	2
22	data-governance	Gouvernance et qualité des données	["Gouvernance et qualité des données", "data governance", "data quality", "gouvernance des données", "qualité des données"]	f	9	2
23	data-ai-generalist	Généraliste — Data, IA et statistiques	["data intern", "data internship", "artificial intelligence", "intelligence artificielle", "data analytics intern", "IA", "AI"]	t	10	2
24	security-operations	SOC et détection	["SOC et détection", "security operations", "soc analyst", "cyber defense", "security monitoring"]	f	0	3
25	incident-response	Réponse à incident et investigation	["Réponse à incident et investigation", "incident response", "digital forensics", "réponse à incident"]	f	1	3
26	pentesting	Pentest et sécurité offensive	["Pentest et sécurité offensive", "penetration testing", "pentest", "ethical hacking", "offensive security"]	f	2	3
27	application-security	Sécurité applicative	["Sécurité applicative", "application security", "appsec", "sécurité applicative"]	f	3	3
28	cloud-security	Sécurité cloud et infrastructure	["Sécurité cloud et infrastructure", "cloud security", "infrastructure security"]	f	4	3
29	identity-access	Identités et accès	["Identités et accès", "identity and access", "identity access", "iam", "gestion des identités"]	f	5	3
30	cyber-governance	Gouvernance, risques et conformité cyber	["Gouvernance, risques et conformité cyber", "cyber governance", "cybersecurity governance", "grc cyber", "information security risk"]	f	6	3
31	cryptography	Cryptographie et recherche sécurité	["Cryptographie et recherche sécurité", "cryptography", "cryptographie"]	f	7	3
32	cybersecurity-generalist	Généraliste — Cybersécurité	["cybersecurity", "cyber security", "cybersécurité", "information security", "it security"]	t	8	3
33	mechanical	Mécanique	["Mécanique", "mechanical", "mécanique", "maschinenbau", "mechanik"]	f	0	4
34	electronics	Électronique	["Électronique", "electronics", "electronic design", "elektronik", "électronique"]	f	1	4
35	electrical	Électrotechnique	["Électrotechnique", "electrical engineer", "electrical engineering", "elektrotechnik", "électrotechnique", "génie électrique"]	f	2	4
36	control-engineering	Automatique et contrôle	["Automatique et contrôle", "control engineering", "control systems", "automatique", "regelungstechnik"]	f	3	4
37	robotics	Robotique et mécatronique	["Robotique et mécatronique", "robotics", "robotique", "mechatronics", "mécatronique"]	f	4	4
38	telecommunications	Télécommunications	["Télécommunications", "telecommunications", "télécommunications", "telecom"]	f	5	4
39	materials-engineering	Matériaux	["Matériaux", "materials engineer", "ingénieur matériaux"]	f	6	4
40	simulation	Simulation et calcul	["Simulation et calcul", "simulation engineer", "numerical simulation", "simulation numérique", "calcul mécanique"]	f	7	4
41	systems-testing	Systèmes et essais	["Systèmes et essais", "systems engineering", "system engineering", "systems test", "test engineer", "ingénierie système"]	f	8	4
42	process-engineering	Conception de procédés	["Conception de procédés", "process engineer", "process engineering", "génie des procédés"]	f	9	4
43	engineering-generalist	Généraliste — Ingénierie et conception technique	["engineering intern", "engineer intern", "ingénieur", "ingénierie", "ingenieur", "engineering internship"]	t	10	4
44	manufacturing	Production et fabrication	["Production et fabrication", "manufacturing", "production industrielle", "fertigung"]	f	0	5
45	industrial-methods	Méthodes et industrialisation	["Méthodes et industrialisation", "industrial engineering", "industrialisation", "méthodes industrielles"]	f	1	5
46	continuous-improvement	Amélioration continue	["Amélioration continue", "continuous improvement", "lean manufacturing", "amélioration continue"]	f	2	5
47	quality-metrology	Qualité et métrologie	["Qualité et métrologie", "quality engineer", "quality management", "quality assurance", "métrologie", "qualité industrielle", "qualitätsmanagement", "qualitaetsmanagement", "qualitätsprüfung"]	f	3	5
48	maintenance	Maintenance et fiabilité	["Maintenance et fiabilité", "maintenance engineer", "maintenance industrielle", "instandhaltung"]	f	4	5
49	safety	Hygiène et sécurité au travail	["Hygiène et sécurité au travail", "occupational safety", "health and safety", "hse", "ehs", "sécurité au travail"]	f	5	5
50	production-planning	Planification industrielle	["Planification industrielle", "production planning", "planification industrielle"]	f	6	5
51	industrial-operations-generalist	Généraliste — Production, qualité et maintenance	["industrial operations", "industrie", "industrial intern", "production intern", "quality intern"]	t	7	5
52	civil-engineering	Génie civil et structures	["Génie civil et structures", "civil engineering", "génie civil", "bauingenieur", "structural engineering"]	f	0	6
53	construction-management	Conduite de travaux	["Conduite de travaux", "construction management", "conduite de travaux", "chantier", "bauleitung", "conducteur de travaux", "conducteur.rice de travaux", "conductrice de travaux"]	f	1	6
54	architecture	Architecture	["Architecture", "architectural", "architecte", "architecture bâtiment"]	f	2	6
55	bim	BIM et modélisation bâtiment	["BIM et modélisation bâtiment", "bim", "building information modeling"]	f	3	6
56	geotechnical	Géotechnique	["Géotechnique", "geotechnical", "géotechnique"]	f	4	6
57	surveying	Topographie	["Topographie", "surveyor", "topographie", "géomètre"]	f	5	6
58	urban-planning	Urbanisme et aménagement	["Urbanisme et aménagement", "urban planning", "urbanisme"]	f	6	6
59	construction-economics	Économie de la construction	["Économie de la construction", "quantity surveyor", "économie de la construction"]	f	7	6
60	construction-generalist	Généraliste — Construction, architecture et urbanisme	["construction", "building intern", "bâtiment"]	t	8	6
61	energy-systems	Systèmes énergétiques	["Systèmes énergétiques", "energy engineering", "systèmes énergétiques", "energietechnik"]	f	0	7
62	renewables	Énergies renouvelables	["Énergies renouvelables", "renewable energy", "énergies renouvelables", "solar energy", "wind energy"]	f	1	7
63	energy-efficiency	Efficacité énergétique	["Efficacité énergétique", "energy efficiency", "efficacité énergétique"]	f	2	7
64	water	Eau et assainissement	["Eau et assainissement", "wastewater", "water treatment", "assainissement", "traitement des eaux"]	f	3	7
65	waste-circular-economy	Déchets et économie circulaire	["Déchets et économie circulaire", "waste management", "circular economy", "économie circulaire"]	f	4	7
66	ecology	Écologie et biodiversité	["Écologie et biodiversité", "ecology", "biodiversity", "écologie", "biodiversité"]	f	5	7
67	carbon-climate	Évaluation carbone et climat	["Évaluation carbone et climat", "carbon accounting", "climate analyst", "bilan carbone", "climat"]	f	6	7
68	environmental-engineering	Ingénierie environnementale	["Ingénierie environnementale", "environmental engineer", "ingénieur environnement"]	f	7	7
69	sustainability	Développement durable et RSE	["Développement durable et RSE", "sustainability", "csr", "rse", "développement durable"]	f	8	7
70	energy-environment-generalist	Généraliste — Énergie et environnement	["environment", "environnement", "energy intern", "énergie"]	t	9	7
71	biology	Biologie et biotechnologies	["Biologie et biotechnologies", "biology", "biologie", "biotechnology", "biotechnologie"]	f	0	8
72	chemistry	Chimie	["Chimie", "chemistry", "chimie", "chemist", "chemiker"]	f	1	8
73	physics	Physique	["Physique", "physics", "physique", "physicist"]	f	2	8
74	applied-mathematics	Mathématiques appliquées	["Mathématiques appliquées", "applied mathematics", "mathématiques appliquées"]	f	3	8
75	geoscience	Géosciences	["Géosciences", "geology", "géologie", "geoscience"]	f	4	8
76	materials-science	Sciences des matériaux	["Sciences des matériaux", "materials science", "sciences des matériaux"]	f	5	8
77	laboratory	Recherche expérimentale et laboratoire	["Recherche expérimentale et laboratoire", "laboratory", "laboratoire", "laboratory technician", "laborantin"]	f	6	8
78	social-science	Sciences humaines et sociales	["Sciences humaines et sociales", "social science", "sciences sociales", "sociologie"]	f	7	8
79	science-research-generalist	Généraliste — Sciences et recherche	["research intern", "research internship", "research assistant", "recherche", "wissenschaft"]	t	8	8
80	clinical-research	Recherche clinique	["Recherche clinique", "clinical research", "recherche clinique", "clinical trials"]	f	0	9
81	public-health	Santé publique et épidémiologie	["Santé publique et épidémiologie", "public health", "santé publique", "epidemiology", "épidémiologie"]	f	1	9
82	health-regulatory	Affaires réglementaires santé	["Affaires réglementaires santé", "pharmaceutical regulatory", "medical regulatory", "affaires réglementaires santé"]	f	2	9
83	pharmacovigilance	Pharmacovigilance	["Pharmacovigilance", "pharmacovigilance", "drug safety"]	f	3	9
84	nursing	Soins et paramédical	["Soins et paramédical", "nursing", "nurse", "infirmier", "infirmière", "paramédical"]	f	4	9
85	psychology	Psychologie	["Psychologie", "psychology", "psychologie", "psychologist"]	f	5	9
86	nutrition	Nutrition et diététique	["Nutrition et diététique", "nutrition", "diététique"]	f	6	9
87	biomedical	Ingénierie biomédicale	["Ingénierie biomédicale", "biomedical", "biomédical"]	f	7	9
88	health-generalist	Généraliste — Santé et recherche clinique	["health intern", "medical", "santé", "healthcare"]	t	8	9
89	corporate-finance	Finance d’entreprise et FP&A	["Finance d’entreprise et FP&A", "corporate finance", "fp&a", "financial planning", "finance d'entreprise"]	f	0	10
90	financial-analysis	Analyse financière	["Analyse financière", "financial analyst", "financial analysis", "analyste financier"]	f	1	10
91	investment-banking	Banque d’investissement et M&A	["Banque d’investissement et M&A", "investment banking", "m&a", "mergers and acquisitions", "fusions acquisitions"]	f	2	10
92	trading	Marchés et trading	["Marchés et trading", "trading", "capital markets", "sales and trading", "marchés financiers"]	f	3	10
93	quantitative-finance	Recherche quantitative	["Recherche quantitative", "quantitative finance", "quantitative analyst", "quant researcher", "finance quantitative"]	f	4	10
94	asset-management	Gestion d’actifs	["Gestion d’actifs", "asset management", "portfolio management", "gestion d'actifs"]	f	5	10
95	private-equity	Capital investissement et venture capital	["Capital investissement et venture capital", "private equity", "venture capital", "capital investissement"]	f	6	10
96	financial-risk	Risques financiers	["Risques financiers", "financial risk", "credit risk", "market risk", "risk analyst", "risques financiers"]	f	7	10
97	credit	Crédit	["Crédit", "credit analyst", "analyse crédit"]	f	8	10
98	actuarial	Actuariat et assurance	["Actuariat et assurance", "actuarial", "actuariat", "actuaire", "insurance analyst"]	f	9	10
99	finance-generalist	Généraliste — Finance, banque et assurance	["finance intern", "finance internship", "finance", "financial intern", "banking", "assurance"]	t	10	10
100	accounting	Comptabilité générale	["Comptabilité générale", "accounting", "accountant", "comptabilité", "comptable", "buchhaltung"]	f	0	11
101	accounts-payable-receivable	Comptabilité fournisseurs et clients	["Comptabilité fournisseurs et clients", "accounts payable", "accounts receivable", "comptabilité fournisseurs", "comptabilité clients"]	f	1	11
102	financial-audit	Audit financier	["Audit financier", "financial audit", "audit financier", "external audit"]	f	2	11
103	management-control	Contrôle de gestion	["Contrôle de gestion", "controlling", "controller", "contrôle de gestion"]	f	3	11
104	tax	Fiscalité	["Fiscalité", "tax", "fiscalité", "steuerrecht"]	f	4	11
105	treasury	Trésorerie	["Trésorerie", "treasury", "trésorerie"]	f	5	11
106	internal-audit	Audit interne et contrôle interne	["Audit interne et contrôle interne", "internal audit", "audit interne", "internal control"]	f	6	11
107	accounting-audit-generalist	Généraliste — Comptabilité, audit et contrôle	["audit intern", "audit internship", "audit", "comptabilité et audit"]	t	7	11
108	business-law	Droit des affaires et contrats	["Droit des affaires et contrats", "business law", "contract law", "droit des affaires", "droit des contrats", "droit commercial"]	f	0	12
109	employment-law	Droit social	["Droit social", "employment law", "labor law", "droit social", "droit du travail"]	f	1	12
110	public-law	Droit public	["Droit public", "public law", "droit public"]	f	2	12
111	intellectual-property	Propriété intellectuelle	["Propriété intellectuelle", "intellectual property", "propriété intellectuelle", "patent law"]	f	3	12
112	data-protection	Protection des données	["Protection des données", "data protection", "privacy officer", "protection des données", "dpo"]	f	4	12
113	regulatory-compliance	Conformité réglementaire	["Conformité réglementaire", "regulatory compliance", "compliance officer", "conformité réglementaire", "compliance"]	f	5	12
114	litigation	Contentieux	["Contentieux", "litigation", "contentieux"]	f	6	12
115	international-law	Droit international et européen	["Droit international et européen", "international law", "european law", "droit international", "droit européen"]	f	7	12
116	legal-compliance-generalist	Généraliste — Droit et conformité	["legal", "juridique", "droit", "rechtswissenschaft", "recht", "juriste", "law intern", "law internship"]	t	8	12
117	corporate-strategy	Stratégie d’entreprise	["Stratégie d’entreprise", "corporate strategy", "business strategy", "stratégie d'entreprise"]	f	0	13
118	management-consulting	Conseil en management	["Conseil en management", "management consulting", "strategy consulting", "conseil en management"]	f	1	13
119	process-consulting	Conseil en organisation et processus	["Conseil en organisation et processus", "process consulting", "organisation et processus"]	f	2	13
120	transformation	Transformation	["Transformation", "digital transformation", "business transformation", "transformation numérique"]	f	3	13
121	economic-research	Études économiques	["Études économiques", "economic research", "economist", "études économiques", "économiste"]	f	4	13
122	policy-consulting	Conseil en politiques publiques	["Conseil en politiques publiques", "policy consulting", "conseil en politiques publiques"]	f	5	13
123	business-analysis	Business analysis	["Business analysis", "business analyst", "business analysis"]	f	6	13
124	change-management	Conduite du changement	["Conduite du changement", "change management", "conduite du changement"]	f	7	13
125	consulting-strategy-generalist	Généraliste — Conseil, stratégie et organisation	["consulting", "consultant", "conseil", "strategy intern", "stratégie"]	t	8	13
126	product-management	Product management	["Product management", "product manager", "product management", "product owner", "chef de produit digital"]	f	0	14
127	product-operations	Product operations	["Product operations", "product operations", "product ops"]	f	1	14
128	digital-project	Gestion de projet numérique	["Gestion de projet numérique", "digital project", "it project", "projet numérique", "projet informatique"]	f	2	14
129	pmo	PMO	["PMO", "pmo", "project management office"]	f	3	14
130	project-management	Gestion de projet généraliste	["Gestion de projet généraliste", "project manager", "project management", "chef de projet", "gestion de projet"]	f	4	14
131	program-coordination	Coordination de programmes	["Coordination de programmes", "program coordinator", "programme coordinator", "coordination de programmes"]	f	5	14
132	agile	Méthodes agiles et facilitation	["Méthodes agiles et facilitation", "agile coach", "scrum master", "agile facilitation"]	f	6	14
133	product-project-generalist	Généraliste — Produit et gestion de projet	["project intern", "projet", "product intern", "programme intern"]	t	7	14
134	strategic-marketing	Marketing stratégique	["Marketing stratégique", "strategic marketing", "marketing stratégique"]	f	0	15
135	market-research	Études de marché	["Études de marché", "market research", "consumer insights", "études de marché"]	f	1	15
136	product-marketing	Marketing produit	["Marketing produit", "product marketing", "chef de produit marketing"]	f	2	15
137	brand-management	Brand management	["Brand management", "brand management", "brand manager", "chef de marque"]	f	3	15
138	growth	Growth et acquisition	["Growth et acquisition", "growth marketing", "growth", "performance marketing", "acquisition marketing"]	f	4	15
139	seo-sea	SEO et SEA	["SEO et SEA", "seo", "sea", "search engine optimization", "paid search"]	f	5	15
140	crm-marketing	CRM et fidélisation	["CRM et fidélisation", "crm marketing", "email marketing", "emailing", "fidélisation", "customer relationship marketing"]	f	6	15
141	content-marketing	Marketing de contenu	["Marketing de contenu", "content marketing", "marketing de contenu"]	f	7	15
142	operational-marketing	Marketing opérationnel	["Marketing opérationnel", "operational marketing", "trade marketing", "marketing opérationnel"]	f	8	15
143	ecommerce	E-commerce et merchandising numérique	["E-commerce et merchandising numérique", "ecommerce", "e-commerce", "merchandising numérique"]	f	9	15
144	marketing-generalist	Généraliste — Marketing et acquisition	["marketing", "market intern", "chef de produit", "chef.fe de produit", "chef·fe de produit"]	t	10	15
145	internal-communication	Communication interne	["Communication interne", "internal communications", "communication interne"]	f	0	16
146	external-communication	Communication externe	["Communication externe", "external communications", "communication externe"]	f	1	16
147	press-relations	Relations presse	["Relations presse", "press relations", "relations presse", "press officer"]	f	2	16
148	public-relations	Relations publiques	["Relations publiques", "public relations", "relations publiques"]	f	3	16
149	social-media	Réseaux sociaux et community management	["Réseaux sociaux et community management", "social media", "community manager", "community management", "réseaux sociaux"]	f	4	16
150	journalism	Journalisme	["Journalisme", "journalism", "journalist", "journalisme", "journaliste"]	f	5	16
151	writing-editing	Rédaction et édition	["Rédaction et édition", "editorial", "copywriting", "rédaction", "édition"]	f	6	16
152	event-communication	Communication événementielle	["Communication événementielle", "event communications", "communication événementielle"]	f	7	16
153	translation	Traduction et localisation	["Traduction et localisation", "translation", "translator", "traduction", "traducteur", "localisation linguistique"]	f	8	16
154	communication-media-generalist	Généraliste — Communication, médias et rédaction	["communication", "communications", "media intern", "médias"]	t	9	16
155	business-development	Business development	["Business development", "business development", "business developer", "développement commercial"]	f	0	17
156	b2b-sales	Vente B2B	["Vente B2B", "b2b sales", "sales development", "vente b2b"]	f	1	17
157	retail-sales	Vente et distribution B2C	["Vente et distribution B2C", "retail sales", "vente en magasin", "vendeur", "conseiller de vente"]	f	2	17
158	account-management	Account management	["Account management", "account manager", "account management", "gestion de comptes"]	f	3	17
159	customer-success	Customer success	["Customer success", "customer success"]	f	4	17
160	customer-support	Support client	["Support client", "customer support", "customer service", "service client", "support client", "relation client", "relations clients"]	f	5	17
161	sales-operations	Sales operations	["Sales operations", "sales operations", "sales ops"]	f	6	17
162	international-sales	Commerce international et export	["Commerce international et export", "international sales", "export sales", "commerce international"]	f	7	17
163	sales-customer-generalist	Généraliste — Commerce et relation client	["sales", "commercial", "vente", "vertrieb"]	t	8	17
164	recruitment	Recrutement	["Recrutement", "recruitment", "recruiting", "recruiter", "recrutement", "talent acquisition", "recruiting intern", "rekrutierung", "recrutador"]	f	0	18
165	hr-administration	Administration RH	["Administration RH", "hr administration", "administration rh", "administration du personnel"]	f	1	18
166	payroll	Paie	["Paie", "payroll", "paie", "gestionnaire de paie"]	f	2	18
167	learning-development	Formation et développement	["Formation et développement", "learning and development", "talent development", "formation rh"]	f	3	18
168	employee-relations	Relations sociales	["Relations sociales", "employee relations", "labor relations", "relations sociales"]	f	4	18
169	people-analytics	People analytics	["People analytics", "people analytics", "hr analytics"]	f	5	18
170	talent-management	Mobilité et gestion des talents	["Mobilité et gestion des talents", "talent management", "gestion des talents", "mobilité rh"]	f	6	18
171	employer-branding	Marque employeur	["Marque employeur", "employer branding", "marque employeur"]	f	7	18
172	human-resources-generalist	Généraliste — Ressources humaines	["human resources", "human resource", "ressources humaines", "hr intern", "rh", "personalwesen"]	t	8	18
173	procurement	Achats	["Achats", "procurement", "purchasing", "buyer", "achats", "acheteur", "einkauf"]	f	0	19
174	supplier-sourcing	Sourcing fournisseurs	["Sourcing fournisseurs", "supplier sourcing", "sourcing fournisseurs"]	f	1	19
175	supply-chain	Supply chain	["Supply chain", "supply chain", "supply-chain"]	f	2	19
176	demand-planning	Prévision de la demande	["Prévision de la demande", "demand planning", "demand planner", "prévision de la demande"]	f	3	19
177	logistics	Logistique et entreposage	["Logistique et entreposage", "logistics", "logistique", "logistik", "warehouse"]	f	4	19
178	transport	Transport	["Transport", "transport planning", "transport operations", "gestion du transport"]	f	5	19
179	customs	Import-export et douanes	["Import-export et douanes", "customs", "douanes", "import export"]	f	6	19
180	supply-planning	Planification des approvisionnements	["Planification des approvisionnements", "supply planning", "supply planner", "approvisionnements"]	f	7	19
181	supply-chain-generalist	Généraliste — Achats, logistique et transport	["operations logistics", "logistics intern", "logistique", "supply chain intern"]	t	8	19
182	ux-research	UX research	["UX research", "ux research", "user research", "recherche utilisateur"]	f	0	20
183	ux-design	UX design	["UX design", "ux design", "ux designer", "user experience design"]	f	1	20
184	ui-design	UI et product design	["UI et product design", "ui design", "ui designer", "product designer", "product design", "design d'interface"]	f	2	20
185	graphic-design	Design graphique	["Design graphique", "graphic design", "graphic designer", "graphisme", "graphiste"]	f	3	20
186	motion-design	Motion design et animation	["Motion design et animation", "motion design", "motion designer", "animation 3d"]	f	4	20
187	industrial-design	Design industriel	["Design industriel", "industrial design", "design industriel"]	f	5	20
188	fashion-design	Mode et textile	["Mode et textile", "fashion design", "fashion designer", "design textile", "styliste"]	f	6	20
189	photography	Photographie	["Photographie", "photography", "photographe", "photographie"]	f	7	20
190	video-production	Vidéo et production audiovisuelle	["Vidéo et production audiovisuelle", "video production", "audiovisuel", "vidéaste", "montage vidéo"]	f	8	20
191	audio-production	Son et musique	["Son et musique", "sound design", "audio production", "production sonore"]	f	9	20
192	design-creative-generalist	Généraliste — Design, création et audiovisuel	["design", "creative", "arts", "création"]	t	10	20
193	agronomy	Agronomie	["Agronomie", "agronomy", "agronomie"]	f	0	21
194	crop-production	Productions végétales	["Productions végétales", "crop production", "productions végétales"]	f	1	21
195	animal-production	Productions animales	["Productions animales", "animal production", "productions animales"]	f	2	21
196	agroecology	Agroécologie	["Agroécologie", "agroecology", "agroécologie"]	f	3	21
197	food-research	R&D alimentaire	["R&D alimentaire", "food science", "food research", "food development", "r&d alimentaire"]	f	4	21
198	food-quality	Qualité et sécurité alimentaire	["Qualité et sécurité alimentaire", "food quality", "food safety", "sécurité alimentaire"]	f	5	21
199	forestry	Gestion forestière	["Gestion forestière", "forestry", "gestion forestière"]	f	6	21
200	animal-care	Santé et soins animaliers	["Santé et soins animaliers", "veterinary", "vétérinaire", "animal care"]	f	7	21
201	agriculture-food-generalist	Généraliste — Agriculture, alimentation et animal	["agriculture", "agricole", "agroalimentaire", "agricultural"]	t	8	21
202	reception	Accueil et réception	["Accueil et réception", "receptionist", "front desk", "réceptionniste"]	f	0	22
203	hotel-management	Gestion hôtelière	["Gestion hôtelière", "hotel management", "hospitality management", "gestion hôtelière"]	f	1	22
204	catering	Restauration et cuisine	["Restauration et cuisine", "catering", "chef cuisinier", "cuisine", "restauration"]	f	2	22
205	travel-tourism	Tourisme et voyages	["Tourisme et voyages", "travel agent", "tourism", "tourisme", "travel consultant"]	f	3	22
206	event-management	Gestion d’événements	["Gestion d’événements", "event management", "event planner", "gestion d'événements", "événementiel"]	f	4	22
207	revenue-management	Revenue management	["Revenue management", "revenue management", "revenue manager"]	f	5	22
208	leisure	Loisirs et animation	["Loisirs et animation", "leisure", "loisirs", "animation touristique"]	f	6	22
209	hospitality-tourism-generalist	Généraliste — Hôtellerie, restauration et tourisme	["hospitality", "hôtellerie", "tourisme", "hotel", "hotellerie"]	t	7	22
210	teaching	Enseignement et pédagogie	["Enseignement et pédagogie", "teaching", "teacher", "enseignement", "pédagogie"]	f	0	23
211	learning-design	Ingénierie de formation	["Ingénierie de formation", "instructional design", "learning design", "ingénierie de formation"]	f	1	23
212	social-work	Accompagnement social	["Accompagnement social", "social work", "social worker", "accompagnement social"]	f	2	23
213	career-guidance	Insertion et orientation	["Insertion et orientation", "career guidance", "orientation professionnelle", "insertion professionnelle"]	f	3	23
214	humanitarian	Action humanitaire	["Action humanitaire", "humanitarian", "humanitaire"]	f	4	23
215	international-relations	Relations internationales et coopération	["Relations internationales et coopération", "international relations", "relations internationales"]	f	5	23
216	public-administration	Administration publique	["Administration publique", "public administration", "administration publique"]	f	6	23
217	local-development	Développement territorial	["Développement territorial", "local development", "développement territorial"]	f	7	23
218	cultural-mediation	Médiation culturelle	["Médiation culturelle", "cultural mediation", "médiation culturelle"]	f	8	23
219	nonprofit-projects	Gestion de projets associatifs	["Gestion de projets associatifs", "nonprofit project", "projets associatifs"]	f	9	23
220	education-social-public-generalist	Généraliste — Éducation, social et action publique	["nonprofit", "non-profit", "ngo", "ong", "public policy", "education intern", "social intern"]	t	10	23
221	administration	Assistanat et coordination administrative	["Assistanat et coordination administrative", "administrative assistant", "administration assistant", "assistanat administratif", "assistant administratif"]	f	0	24
222	document-management	Gestion documentaire	["Gestion documentaire", "document management", "gestion documentaire", "documentaliste"]	f	1	24
223	business-operations	Gestion des opérations générales	["Gestion des opérations générales", "business operations", "operations intern", "opérations générales"]	f	2	24
224	office-management	Office management	["Office management", "office management", "office manager"]	f	3	24
225	real-estate-management	Gestion immobilière	["Gestion immobilière", "real estate management", "gestion immobilière"]	f	4	24
226	real-estate-investment	Analyse et investissement immobilier	["Analyse et investissement immobilier", "real estate investment", "immobilier investissement"]	f	5	24
227	property-management	Gestion locative	["Gestion locative", "property management", "gestion locative"]	f	6	24
228	facilities-management	Gestion des services et installations	["Gestion des services et installations", "facilities management", "facility management", "services généraux"]	f	7	24
229	administration-real-estate-generalist	Généraliste — Administration, gestion et immobilier	["administration", "administrative", "immobilier", "real estate"]	t	8	24
\.


--
-- Data for Name: jobboard_role; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_role (id, name, slug) FROM stdin;
\.


--
-- Data for Name: jobboard_offer; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_offer (id, title, company_id, description, application_url, created_at, role_id, contract_type, work_mode, employment_schedule, expires_at, language_code, published_at, remote_scope, seniority, status, updated_at, search_document, search_title, taxonomy_evidence, taxonomy_input_hash, taxonomy_manual, taxonomy_status, taxonomy_version, job_subdomain_id) FROM stdin;
1	Stage développement Python	1	Stage fictif de six mois en France. Travail accompagné, documentation et tests. Aucune candidature réelle ne sera envoyée.		2026-10-11 15:05:14.084709+02	\N	internship	unknown	unknown	\N	\N	2026-10-11 15:05:14.084261+02	\N	unknown	open	2026-10-11 15:05:14.084715+02	'accompagne':14C 'atelier':4A 'aucune':18C 'candidature':19C 'de':8C 'demo':5A 'developpement':2A 'documentation':15C 'en':11C 'envoyee':23C 'et':16C 'fictif':7C 'france':12C 'mois':10C 'ne':21C 'python':3A 'reelle':20C 'sera':22C 'six':9C 'stage':1A,6C 'tests':17C 'travail':13C	stage developpement python	{}		f	unclassified		\N
2	Stage interfaces React	1	Stage fictif de six mois en France. Travail accompagné, documentation et tests. Aucune candidature réelle ne sera envoyée.		2026-10-11 15:05:14.102875+02	\N	internship	unknown	unknown	\N	\N	2026-10-11 15:05:14.10251+02	\N	unknown	open	2026-10-11 15:05:14.10288+02	'accompagne':14C 'atelier':4A 'aucune':18C 'candidature':19C 'de':8C 'demo':5A 'documentation':15C 'en':11C 'envoyee':23C 'et':16C 'fictif':7C 'france':12C 'interfaces':2A 'mois':10C 'ne':21C 'react':3A 'reelle':20C 'sera':22C 'six':9C 'stage':1A,6C 'tests':17C 'travail':13C	stage interfaces react	{}		f	unclassified		\N
3	Stage analyse de données	2	Stage fictif de six mois en France. Travail accompagné, documentation et tests. Aucune candidature réelle ne sera envoyée.		2026-10-11 15:05:14.111716+02	\N	internship	unknown	unknown	\N	\N	2026-10-11 15:05:14.111308+02	\N	unknown	open	2026-10-11 15:05:14.111723+02	'accompagne':15C 'analyse':2A 'aucune':19C 'candidature':20C 'de':3A,9C 'documentation':16C 'donnees':4A 'en':12C 'envoyee':24C 'et':17C 'exemple':6A 'fictif':8C 'france':13C 'laboratoire':5A 'mois':11C 'ne':22C 'reelle':21C 'sera':23C 'six':10C 'stage':1A,7C 'tests':18C 'travail':14C	stage analyse de donnees	{}		f	unclassified		\N
4	Stage administration systèmes	2	Stage fictif de six mois en France. Travail accompagné, documentation et tests. Aucune candidature réelle ne sera envoyée.		2026-10-11 15:05:14.121827+02	\N	internship	unknown	unknown	\N	\N	2026-10-11 15:05:14.121355+02	\N	unknown	open	2026-10-11 15:05:14.121834+02	'accompagne':14C 'administration':2A 'aucune':18C 'candidature':19C 'de':8C 'documentation':15C 'en':11C 'envoyee':23C 'et':16C 'exemple':5A 'fictif':7C 'france':12C 'laboratoire':4A 'mois':10C 'ne':21C 'reelle':20C 'sera':22C 'six':9C 'stage':1A,6C 'systemes':3A 'tests':17C 'travail':13C	stage administration systemes	{}		f	unclassified		\N
\.


--
-- Data for Name: jobboard_offersource; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_offersource (id, external_id, external_requisition_id, origin_url, apply_url, source_status, first_seen_at, last_seen_at, last_checked_at, content_hash, raw_payload, raw_expires_at, last_seen_run_id, offer_id, board_id) FROM stdin;
1	1	\N	https://example.test/stages/1	https://example.test/stages/1	active	2026-10-11 15:05:14.097674+02	2026-10-11 15:05:14.097678+02	2026-10-11 15:05:14.09754+02	34056b253132c60bb866e4da5c8689fa3f7f8da725494df92e7dd160a67e1063	{}	\N	\N	1	1
2	2	\N	https://example.test/stages/2	https://example.test/stages/2	active	2026-10-11 15:05:14.108677+02	2026-10-11 15:05:14.10868+02	2026-10-11 15:05:14.108612+02	0c0e0f7c2e226cb6c7bd57837d07c016faf463a8e0f2b2ff31a7cd830704469d	{}	\N	\N	2	2
3	3	\N	https://example.test/stages/3	https://example.test/stages/3	active	2026-10-11 15:05:14.118525+02	2026-10-11 15:05:14.118531+02	2026-10-11 15:05:14.118434+02	d50487760b8ec2f3d4493cfea7a2b6df178816d10492db8807071e829f4dbd76	{}	\N	\N	3	3
4	4	\N	https://example.test/stages/4	https://example.test/stages/4	active	2026-10-11 15:05:14.126956+02	2026-10-11 15:05:14.126959+02	2026-10-11 15:05:14.126894+02	0d91278ec519416617d007933bc3cecb704fbaf28a979ed90d11fe09752e1278	{}	\N	\N	4	3
\.


--
-- Data for Name: jobboard_application; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_application (id, status, submitted_at, external_reference, created_at, updated_at, offer_id, source_id, user_id) FROM stdin;
1	submitted	2026-10-11 15:05:14.128948+02	\N	2026-10-11 15:05:14.129303+02	2026-10-11 15:05:14.12931+02	1	1	1
2	submitted	2026-10-11 15:05:14.13522+02	\N	2026-10-11 15:05:14.135644+02	2026-10-11 15:05:14.13566+02	2	2	2
\.


--
-- Data for Name: jobboard_applicationrevision; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_applicationrevision (id, revision_no, schema_version, profile_snapshot, offer_snapshot, form_snapshot, answers, generator_version, prompt_version, content_hash, sealed_at, created_at, application_id, user_id) FROM stdin;
\.


--
-- Data for Name: jobboard_document; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_document (id, kind, origin, bucket, object_key, original_name, mime_type, byte_size, sha256, status, created_at, derived_from_id, owner_id) FROM stdin;
1	resume	upload	local	dev/alice/cv.pdf	cv_fictif.pdf	application/pdf	3582	16feabe9404c9794c32f493c480ff4f6188099d6c41a9b4e82d0bc11c5bd602b	ready	2026-10-11 15:05:11.474317+02	\N	1
2	resume	upload	local	dev/bob/cv.pdf	cv_fictif.pdf	application/pdf	3582	16feabe9404c9794c32f493c480ff4f6188099d6c41a9b4e82d0bc11c5bd602b	ready	2026-10-11 15:05:11.849816+02	\N	2
3	resume	upload	local	dev/vide/cv.pdf	cv_fictif.pdf	application/pdf	3582	16feabe9404c9794c32f493c480ff4f6188099d6c41a9b4e82d0bc11c5bd602b	ready	2026-10-11 15:05:12.248291+02	\N	3
\.


--
-- Data for Name: jobboard_submissionauthorization; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_submissionauthorization (id, approved_hash, mode, granted_at, expires_at, revoked_at, application_id, revision_id, user_id) FROM stdin;
\.


--
-- Data for Name: jobboard_agentrun; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_agentrun (id, purpose, status, phase, idempotency_key, worker_token, lease_expires_at, heartbeat_at, attempt_no, adapter_version, error_code, external_receipt, started_at, finished_at, created_at, evidence_document_id, user_id, application_id, revision_id, authorization_id) FROM stdin;
\.


--
-- Data for Name: jobboard_alertevent; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_alertevent (id, event_key, channel, payload, created_at, read_at, offer_id, user_id) FROM stdin;
\.


--
-- Data for Name: jobboard_applicationevent; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_applicationevent (id, kind, origin, status_after, happened_at, recorded_at, dedupe_key, payload, application_id, run_id) FROM stdin;
\.


--
-- Data for Name: jobboard_applicationtask; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_applicationtask (id, title, due_at, completed_at, created_at, application_id) FROM stdin;
\.


--
-- Data for Name: jobboard_sourcecandidate; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_sourcecandidate (id, url, provider, board_key, instance, status, company_name, discovered_at, board_id) FROM stdin;
\.


--
-- Data for Name: jobboard_atsprobe; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_atsprobe (id, enabled, state, attempts, next_attempt_at, last_attempt_at, lease_token, lease_expires_at, error_code, result, candidate_id) FROM stdin;
\.


--
-- Data for Name: jobboard_boardschedule; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_boardschedule (id, interval_minutes, next_run_at, failure_count, lease_token, lease_expires_at, last_error_code, missing_confirmation_hours, paused, quarantine_hash, quarantine_since, board_id, collection_checkpoint) FROM stdin;
\.


--
-- Data for Name: jobboard_location; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_location (id, name, canonical_key, city, country_code, region) FROM stdin;
1	Paris	dev-paris-fr	Paris	FR	\N
\.


--
-- Data for Name: jobboard_candidateprofile; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_candidateprofile (id, full_name, phone, location_text, resume_url, user_id, presentation, available_from, created_at, current_resume_kind, first_name, github_url, headline, last_name, linkedin_url, location_id, portfolio_url, profile_version, updated_at, current_resume_id, citizenships, city, country_code, district, onboarding_completed_at, postal_code, region, street_address) FROM stdin;
1	Alice Exemple				1		\N	2026-10-11 15:05:11.467815+02	resume	\N	\N	\N	\N	\N	\N	\N	1	2026-10-11 15:05:11.46885+02	1	[]	Paris	FR		2026-10-11 15:05:11.467047+02			1 rue de la Démonstration
2	Bob Exemple				2		\N	2026-10-11 15:05:11.847915+02	resume	\N	\N	\N	\N	\N	\N	\N	1	2026-10-11 15:05:11.848255+02	2	[]	Paris	FR		2026-10-11 15:05:11.847779+02			1 rue de la Démonstration
3	Camille Exemple				3		\N	2026-10-11 15:05:12.245988+02	resume	\N	\N	\N	\N	\N	\N	\N	1	2026-10-11 15:05:12.246409+02	3	[]	Paris	FR		2026-10-11 15:05:12.245831+02			1 rue de la Démonstration
4	Dominique Exemple				4		\N	2026-10-11 15:05:12.718908+02	resume	\N	\N	\N	\N	\N	\N	\N	1	2026-10-11 15:05:12.719733+02	\N	[]	Paris	FR		2026-10-11 15:05:12.718638+02			1 rue de la Démonstration
\.


--
-- Data for Name: jobboard_skill; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_skill (id, name, slug) FROM stdin;
\.


--
-- Data for Name: jobboard_candidateprofile_skills; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_candidateprofile_skills (id, candidateprofile_id, skill_id) FROM stdin;
\.


--
-- Data for Name: jobboard_companypreference; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_companypreference (id, excluded, company_id, user_id) FROM stdin;
\.


--
-- Data for Name: jobboard_companyprofile; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_companyprofile (id, facts, sections, updated_at, company_id) FROM stdin;
\.


--
-- Data for Name: jobboard_compensationband; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_compensationband (id, label, minimum, maximum, currency, period, gross_net, location_id, offer_id, source_id) FROM stdin;
\.


--
-- Data for Name: jobboard_deletionrequest; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_deletionrequest (id, status, requested_at, completed_at, last_error_code, user_id) FROM stdin;
\.


--
-- Data for Name: jobboard_discoveryquery; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_discoveryquery (id, provider, country, language, domain, term, enabled, cursor, next_run_at, last_success_at, last_error_code, failure_count, result_count, total_available, truncated, lease_token, lease_expires_at, auto_activate) FROM stdin;
\.


--
-- Data for Name: jobboard_discoveryresult; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_discoveryresult (id, external_id, source_url, company_name, payload, attribution, status, error_code, last_attempt_at, first_seen_at, last_seen_at, candidate_id, query_id) FROM stdin;
\.


--
-- Data for Name: jobboard_education; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_education (id, institution, degree, field_of_study, start_date, end_date, is_current, date_precision, description, "position", profile_id) FROM stdin;
\.


--
-- Data for Name: jobboard_experience; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_experience (id, company_name, title, start_date, end_date, is_current, date_precision, description, "position", profile_id) FROM stdin;
\.


--
-- Data for Name: jobboard_externalopportunity; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_externalopportunity (id, url, title, company_name, description, status, error_code, created_at, updated_at, offer_id, user_id) FROM stdin;
\.


--
-- Data for Name: jobboard_interview; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_interview (id, title, starts_at, ends_at, display_timezone, meeting_url, location_text, status, notes, application_id) FROM stdin;
\.


--
-- Data for Name: jobboard_offer_locations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_offer_locations (id, offer_id, location_id) FROM stdin;
1	1	1
2	2	1
3	3	1
4	4	1
\.


--
-- Data for Name: jobboard_offer_secondary_subdomains; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_offer_secondary_subdomains (id, offer_id, jobsubdomain_id) FROM stdin;
\.


--
-- Data for Name: jobboard_offer_skills; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_offer_skills (id, offer_id, skill_id, importance) FROM stdin;
\.


--
-- Data for Name: jobboard_offerenrichment; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_offerenrichment (id, content_version, semantic_hash, domain, facts, classification, country_codes, europe_status, extractor_version, offer_id, event_at, content) FROM stdin;
1	1			{"demo": true}	confirmed	["FR"]	in_scope	dev-fixture	1	2026-10-11 15:05:14.099455+02	{}
2	1			{"demo": true}	confirmed	["FR"]	in_scope	dev-fixture	2	2026-10-11 15:05:14.109498+02	{}
3	1			{"demo": true}	confirmed	["FR"]	in_scope	dev-fixture	3	2026-10-11 15:05:14.119943+02	{}
4	1			{"demo": true}	confirmed	["FR"]	in_scope	dev-fixture	4	2026-10-11 15:05:14.127997+02	{}
\.


--
-- Data for Name: jobboard_offerfeedback; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_offerfeedback (id, reason, created_at, offer_id, user_id) FROM stdin;
\.


--
-- Data for Name: jobboard_offermergedecision; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_offermergedecision (id, status, evidence, created_at, resolved_at, canonical_offer_id, duplicate_offer_id) FROM stdin;
\.


--
-- Data for Name: jobboard_offerreport; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_offerreport (id, reason, details, created_at, status, offer_id, user_id) FROM stdin;
\.


--
-- Data for Name: jobboard_outboxmessage; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_outboxmessage (id, topic, dedupe_key, payload, available_at, processed_at, attempts, lease_token, lease_expires_at, last_error_code, created_at, owner_id) FROM stdin;
\.


--
-- Data for Name: jobboard_searchpreference; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_searchpreference (id, profile_id, minimum_salary, salary_currency, salary_gross_net, salary_period, updated_at, willing_to_relocate) FROM stdin;
\.


--
-- Data for Name: jobboard_preferencecontract; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_preferencecontract (id, value, preference_id) FROM stdin;
\.


--
-- Data for Name: jobboard_preferenceworkmode; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_preferenceworkmode (id, value, preference_id) FROM stdin;
\.


--
-- Data for Name: jobboard_project; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_project (id, title, description, url, "position", profile_id) FROM stdin;
\.


--
-- Data for Name: jobboard_recruiterprofile; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_recruiterprofile (id, full_name, company_name, siren, website_url, linkedin_url, verification_status, email_verified, email_code_hash, email_code_expires_at, updated_at, company_id, user_id) FROM stdin;
1	Elise Exemple	Atelier Démo				verified	t		\N	2026-10-11 15:05:13.449329+02	1	6
2	Farid Exemple	Atelier Démo				verified	t		\N	2026-10-11 15:05:13.769153+02	1	7
3	Gaelle Exemple	Atelier Démo				unverified	f		\N	2026-10-11 15:05:14.0826+02	1	8
\.


--
-- Data for Name: jobboard_recruiterjob; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_recruiterjob (id, title, department, contract_type, location, country_code, work_mode, salary, description, skills, education, languages, status, origin, views, published_at, created_at, updated_at, offer_id, owner_id) FROM stdin;
1	Stage développement Python		internship	Paris	FR	onsite		Stage fictif de six mois en France. Travail accompagné, documentation et tests. Aucune candidature réelle ne sera envoyée.				active	direct	0	2026-10-11 15:05:14.100998+02	2026-10-11 15:05:14.101389+02	2026-10-11 15:05:14.101395+02	1	1
2	Stage interfaces React		internship	Paris	FR	onsite		Stage fictif de six mois en France. Travail accompagné, documentation et tests. Aucune candidature réelle ne sera envoyée.				active	direct	0	2026-10-11 15:05:14.110172+02	2026-10-11 15:05:14.110462+02	2026-10-11 15:05:14.110469+02	2	2
\.


--
-- Data for Name: jobboard_recruiterapplicant; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_recruiterapplicant (id, profile_snapshot, stage, match_score, ai_summary, rejection_reason, interview_at, updated_at, application_id, resume_id, job_id, candidate_id, offer_id, resume_kind) FROM stdin;
1	{"demo": true, "email": "alice@example.test", "full_name": "Alice Exemple"}	new	\N			\N	2026-10-11 15:05:14.131553+02	1	1	1	1	1	resume
2	{"demo": true, "email": "bob@example.test", "full_name": "Bob Exemple"}	new	\N			\N	2026-10-11 15:05:14.137311+02	2	2	2	2	2	resume
\.


--
-- Data for Name: jobboard_recruiterintegration; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_recruiterintegration (id, provider, url, status, updated_at, owner_id) FROM stdin;
\.


--
-- Data for Name: jobboard_requestthrottle; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_requestthrottle (id, key, count, expires_at) FROM stdin;
\.


--
-- Data for Name: jobboard_revisiondocument; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_revisiondocument (id, purpose, document_id, revision_id, user_id) FROM stdin;
\.


--
-- Data for Name: jobboard_savedoffer; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_savedoffer (id, created_at, offer_id, user_id) FROM stdin;
1	2026-10-11 15:05:14.133792+02	1	1
2	2026-10-11 15:05:14.139026+02	2	2
\.


--
-- Data for Name: jobboard_savedsearch; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_savedsearch (id, name, criteria, frequency, timezone, version, created_at, updated_at, last_evaluated_at, user_id) FROM stdin;
\.


--
-- Data for Name: jobboard_searchpreference_excluded_job_subdomains; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_searchpreference_excluded_job_subdomains (id, searchpreference_id, jobsubdomain_id) FROM stdin;
\.


--
-- Data for Name: jobboard_searchpreference_job_domains; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_searchpreference_job_domains (id, searchpreference_id, jobdomain_id) FROM stdin;
\.


--
-- Data for Name: jobboard_searchpreference_job_subdomains; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_searchpreference_job_subdomains (id, searchpreference_id, jobsubdomain_id) FROM stdin;
\.


--
-- Data for Name: jobboard_searchpreference_locations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_searchpreference_locations (id, searchpreference_id, location_id) FROM stdin;
\.


--
-- Data for Name: jobboard_searchpreference_roles; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_searchpreference_roles (id, searchpreference_id, role_id) FROM stdin;
\.


--
-- Data for Name: jobboard_sourcediscoveryseed; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_sourcediscoveryseed (id, url, allowed_host, company_name, enabled, next_run_at, last_success_at, failure_count, last_error_code, lease_token, lease_expires_at) FROM stdin;
\.


--
-- Data for Name: jobboard_sourceobservation; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_sourceobservation (id, missing_since, missing_count, source_id) FROM stdin;
\.


--
-- Data for Name: jobboard_sourcerevision; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_sourcerevision (id, raw_hash, semantic_hash, payload, created_at, source_id) FROM stdin;
\.


--
-- Data for Name: jobboard_workauthorization; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.jobboard_workauthorization (id, country_code, authorized, needs_sponsorship, confirmed_at, profile_id, authorization_basis) FROM stdin;
\.


--
-- Name: auth_group_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.auth_group_id_seq', 1, false);


--
-- Name: auth_group_permissions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.auth_group_permissions_id_seq', 1, false);


--
-- Name: auth_permission_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.auth_permission_id_seq', 256, true);


--
-- Name: auth_user_groups_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.auth_user_groups_id_seq', 1, false);


--
-- Name: auth_user_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.auth_user_id_seq', 8, true);


--
-- Name: auth_user_user_permissions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.auth_user_user_permissions_id_seq', 1, false);


--
-- Name: django_admin_log_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.django_admin_log_id_seq', 1, false);


--
-- Name: django_content_type_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.django_content_type_id_seq', 64, true);


--
-- Name: django_migrations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.django_migrations_id_seq', 52, true);


--
-- Name: jobboard_agentrun_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_agentrun_id_seq', 1, false);


--
-- Name: jobboard_alertevent_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_alertevent_id_seq', 1, false);


--
-- Name: jobboard_application_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_application_id_seq', 2, true);


--
-- Name: jobboard_applicationevent_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_applicationevent_id_seq', 1, false);


--
-- Name: jobboard_applicationrevision_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_applicationrevision_id_seq', 1, false);


--
-- Name: jobboard_applicationtask_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_applicationtask_id_seq', 1, false);


--
-- Name: jobboard_atsprobe_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_atsprobe_id_seq', 1, false);


--
-- Name: jobboard_boardschedule_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_boardschedule_id_seq', 1, false);


--
-- Name: jobboard_candidateprofile_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_candidateprofile_id_seq', 4, true);


--
-- Name: jobboard_candidateprofile_skills_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_candidateprofile_skills_id_seq', 1, false);


--
-- Name: jobboard_company_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_company_id_seq', 3, true);


--
-- Name: jobboard_companypreference_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_companypreference_id_seq', 1, false);


--
-- Name: jobboard_companyprofile_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_companyprofile_id_seq', 1, false);


--
-- Name: jobboard_compensationband_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_compensationband_id_seq', 1, false);


--
-- Name: jobboard_deletionrequest_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_deletionrequest_id_seq', 1, false);


--
-- Name: jobboard_discoveryquery_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_discoveryquery_id_seq', 1, false);


--
-- Name: jobboard_discoveryresult_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_discoveryresult_id_seq', 1, false);


--
-- Name: jobboard_document_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_document_id_seq', 3, true);


--
-- Name: jobboard_education_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_education_id_seq', 1, false);


--
-- Name: jobboard_experience_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_experience_id_seq', 1, false);


--
-- Name: jobboard_externalopportunity_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_externalopportunity_id_seq', 1, false);


--
-- Name: jobboard_importrun_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_importrun_id_seq', 1, false);


--
-- Name: jobboard_interview_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_interview_id_seq', 1, false);


--
-- Name: jobboard_jobdomain_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_jobdomain_id_seq', 24, true);


--
-- Name: jobboard_jobsubdomain_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_jobsubdomain_id_seq', 229, true);


--
-- Name: jobboard_location_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_location_id_seq', 1, true);


--
-- Name: jobboard_offer_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_offer_id_seq', 4, true);


--
-- Name: jobboard_offer_location_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_offer_location_id_seq', 4, true);


--
-- Name: jobboard_offer_secondary_subdomains_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_offer_secondary_subdomains_id_seq', 1, false);


--
-- Name: jobboard_offer_skills_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_offer_skills_id_seq', 1, false);


--
-- Name: jobboard_offerenrichment_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_offerenrichment_id_seq', 4, true);


--
-- Name: jobboard_offerfeedback_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_offerfeedback_id_seq', 1, false);


--
-- Name: jobboard_offermergedecision_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_offermergedecision_id_seq', 1, false);


--
-- Name: jobboard_offerreport_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_offerreport_id_seq', 1, false);


--
-- Name: jobboard_offersource_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_offersource_id_seq', 4, true);


--
-- Name: jobboard_outboxmessage_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_outboxmessage_id_seq', 1, false);


--
-- Name: jobboard_preferencecontract_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_preferencecontract_id_seq', 1, false);


--
-- Name: jobboard_preferenceworkmode_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_preferenceworkmode_id_seq', 1, false);


--
-- Name: jobboard_project_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_project_id_seq', 1, false);


--
-- Name: jobboard_recruiterapplicant_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_recruiterapplicant_id_seq', 2, true);


--
-- Name: jobboard_recruiterintegration_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_recruiterintegration_id_seq', 1, false);


--
-- Name: jobboard_recruiterjob_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_recruiterjob_id_seq', 2, true);


--
-- Name: jobboard_recruiterprofile_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_recruiterprofile_id_seq', 3, true);


--
-- Name: jobboard_requestthrottle_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_requestthrottle_id_seq', 1, false);


--
-- Name: jobboard_revisiondocument_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_revisiondocument_id_seq', 1, false);


--
-- Name: jobboard_role_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_role_id_seq', 1, false);


--
-- Name: jobboard_savedoffer_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_savedoffer_id_seq', 2, true);


--
-- Name: jobboard_savedsearch_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_savedsearch_id_seq', 1, false);


--
-- Name: jobboard_searchpreference_excluded_job_subdomains_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_searchpreference_excluded_job_subdomains_id_seq', 1, false);


--
-- Name: jobboard_searchpreference_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_searchpreference_id_seq', 1, false);


--
-- Name: jobboard_searchpreference_job_domains_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_searchpreference_job_domains_id_seq', 1, false);


--
-- Name: jobboard_searchpreference_job_subdomains_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_searchpreference_job_subdomains_id_seq', 1, false);


--
-- Name: jobboard_searchpreference_locations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_searchpreference_locations_id_seq', 1, false);


--
-- Name: jobboard_searchpreference_roles_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_searchpreference_roles_id_seq', 1, false);


--
-- Name: jobboard_skill_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_skill_id_seq', 1, false);


--
-- Name: jobboard_sourceboard_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_sourceboard_id_seq', 3, true);


--
-- Name: jobboard_sourcecandidate_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_sourcecandidate_id_seq', 1, false);


--
-- Name: jobboard_sourcediscoveryseed_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_sourcediscoveryseed_id_seq', 1, false);


--
-- Name: jobboard_sourceobservation_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_sourceobservation_id_seq', 1, false);


--
-- Name: jobboard_sourcerevision_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_sourcerevision_id_seq', 1, false);


--
-- Name: jobboard_submissionauthorization_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_submissionauthorization_id_seq', 1, false);


--
-- Name: jobboard_workauthorization_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobboard_workauthorization_id_seq', 1, false);


--
-- PostgreSQL database dump complete
--

\unrestrict jekPf1zrgdpzc90EbwNjbj00NRUCdNbcws0rVDdliBMGIKyzNjf4Wyeq7JaKvvL


-- Dates de démonstration locales, sans vérification réseau.
UPDATE jobboard_offersource SET last_checked_at = CURRENT_TIMESTAMP;

COMMIT;
