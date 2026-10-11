-- psql -X -v ON_ERROR_STOP=1 -f donnees/requetes.sql
-- Consultations sans modifier le jeu d'essai.
BEGIN READ ONLY;

-- Q1 / R1 : 3 entreprises, dont Entreprise Sans Offre avec 0 offre.
SELECT c.name, count(o.id) AS offres
FROM jobboard_company c LEFT JOIN jobboard_offer o ON o.company_id = c.id
GROUP BY c.id ORDER BY c.id;

-- Q2 : 4 stages et leur entreprise.
SELECT o.id, o.title, c.name AS entreprise, o.contract_type, o.status
FROM jobboard_offer o JOIN jobboard_company c ON c.id = o.company_id
ORDER BY o.id;

-- Q3 / R2 : Alice voit uniquement son dossier (1 ligne).
-- À l'étape métier, l'identité devra venir de la session serveur.
SELECT a.id, u.username, o.title, a.status
FROM jobboard_application a JOIN auth_user u ON u.id = a.user_id
JOIN jobboard_offer o ON o.id = a.offer_id WHERE u.username = 'alice';

-- Q4 : vide et attente n'ont aucune candidature (2 lignes).
SELECT u.username FROM auth_user u
JOIN jobboard_candidateprofile p ON p.user_id = u.id
LEFT JOIN jobboard_application a ON a.user_id = u.id
WHERE a.id IS NULL ORDER BY u.username;

-- Q5 : 2 offres sans candidature.
SELECT o.title FROM jobboard_offer o
LEFT JOIN jobboard_application a ON a.offer_id = o.id
WHERE a.id IS NULL ORDER BY o.id;

-- Q6 / R3 : 0 source incohérente.
SELECT count(*) AS sources_incoherentes FROM jobboard_application a
JOIN jobboard_offersource s ON s.id = a.source_id WHERE a.offer_id <> s.offer_id;

-- Q7 / R4 : 0 doublon.
SELECT user_id, offer_id, count(*) FROM jobboard_application
GROUP BY user_id, offer_id HAVING count(*) > 1;

-- Q8 / R5 : scrypt pour les 8 comptes, sans exposer les empreintes.
SELECT username, split_part(mot_de_passe_hash, '$', 1) AS algorithme
FROM auth_user ORDER BY id;

-- Q9 / R5 : 0 divergence, la colonne du hash est générée.
SELECT count(*) AS hashes_desynchronises FROM auth_user
WHERE mot_de_passe_hash IS DISTINCT FROM password;

-- Q10 / R6 : attente inactif ; admin seul administrateur.
SELECT username, is_active, is_staff, is_superuser FROM auth_user ORDER BY id;

-- Q11 : 3 recruteurs, 2 vérifiés ; entreprise partagée, espaces distincts.
SELECT u.username, c.name, r.email_verified, r.verification_status,
       count(j.id) AS offres_personnelles
FROM jobboard_recruiterprofile r JOIN auth_user u ON u.id = r.user_id
JOIN jobboard_company c ON c.id = r.company_id
LEFT JOIN jobboard_recruiterjob j ON j.owner_id = r.id
GROUP BY r.id, u.username, c.name ORDER BY r.id;

-- Q12 / R2 : destinataires des 2 dossiers transmis et propriétaire du CV.
SELECT recruiter.username AS destinataire, candidate.username AS candidat,
       j.title, d.owner_id = a.user_id AS cv_du_candidat
FROM jobboard_recruiterapplicant ra
JOIN jobboard_application a ON a.id = ra.application_id
JOIN auth_user candidate ON candidate.id = a.user_id
JOIN jobboard_recruiterjob j ON j.id = ra.job_id
JOIN jobboard_recruiterprofile r ON r.id = j.owner_id
JOIN auth_user recruiter ON recruiter.id = r.user_id
JOIN jobboard_document d ON d.id = ra.resume_id ORDER BY ra.id;

-- Q13 : clés et contraintes principales.
SELECT conrelid::regclass AS table_name, conname, pg_get_constraintdef(oid)
FROM pg_constraint WHERE connamespace = 'public'::regnamespace
AND conrelid::regclass::text IN (
    'auth_user', 'jobboard_offer', 'jobboard_application',
    'jobboard_candidateprofile', 'jobboard_recruiterprofile', 'jobboard_recruiterjob'
) ORDER BY 1, 2;
ROLLBACK;
