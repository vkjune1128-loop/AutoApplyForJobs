"""Tests for ResumeData schema and tailoring helpers."""

from autoapply.config.schemas import Education, Experience, ResumeData


def test_resume_data_schema():
    resume = ResumeData(
        name="John Doe",
        email="john@example.com",
        phone="+91-9876543210",
        summary="Experienced Java Backend Engineer with 5+ years of experience.",
        skills=["Java", "Spring Boot", "Kafka", "SQL", "Docker"],
        experience=[
            Experience(
                company="Tech Corp",
                title="Senior Backend Engineer",
                start_date="2021-01",
                end_date="Present",
                location="Bangalore, India",
                bullets=[
                    "Designed high-throughput microservices using Spring Boot and Kafka, reducing latency by 35%.",
                    "Optimized PostgreSQL queries, cutting p99 response times from 1.2s to 200ms.",
                ],
                technologies=["Java 17", "Spring Boot", "Kafka", "PostgreSQL"],
            )
        ],
        education=[
            Education(
                institution="National Institute of Technology",
                degree="B.Tech",
                field="Computer Science",
                year="2020",
            )
        ],
        certifications=["AWS Certified Developer - Associate"],
    )

    assert resume.name == "John Doe"
    assert len(resume.skills) == 5
    assert len(resume.experience) == 1
    assert "Spring Boot" in resume.experience[0].technologies
