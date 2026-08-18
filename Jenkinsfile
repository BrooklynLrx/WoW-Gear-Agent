pipeline {
    agent any
    triggers { pollSCM('H/5 * * * *') }

    stages {
        stage('Build') {
            steps {
                sh 'docker compose --env-file /opt/wow/.env.production build'
            }
        }
        stage('Database') {
            steps {
                sh 'docker compose --env-file /opt/wow/.env.production up -d --wait mysql'
                sh 'docker compose --env-file /opt/wow/.env.production run --rm backend alembic upgrade head'
                sh 'docker compose --env-file /opt/wow/.env.production run --rm backend python scripts/import_data.py'
            }
        }
        stage('Test') {
            steps {
                sh 'docker compose --env-file /opt/wow/.env.production run --rm backend sh -c "PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q"'
            }
        }
        stage('Deploy') {
            steps {
                sh 'docker compose --env-file /opt/wow/.env.production up -d --remove-orphans backend frontend'
            }
        }
    }

    post {
        always { sh 'docker image prune -f' }
    }
}
