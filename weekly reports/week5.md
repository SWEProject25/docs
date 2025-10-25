# Week 5 Report - Hankers Team

## Frontend Team

**Abdelrahman Adel (Sub Team Leader)**
- Integrated OTP Verification with backend for Create Account and Forget Password flows
- Ensured proper validation and error handling between frontend and backend
- Added and configured Google reCAPTCHA during the Create Account process
- Finalized full integration of account creation flow with backend APIs
- Handled all edge cases and improved user feedback (success and error messages)
- Connected OAuth login with backend (Google and Github)
- Designed and implemented the Forget Password modal UI
- Ensured proper user flow to OTP verification and password reset

**Ahmed Fathy**
- Completed profile page header with avatar, cover, user info, description and bio
- Implemented edit profile modal functionality
- Updated reusable components including modal and tabs
- Implemented Zustand for update profile data and delete operations

**Mohamed Emad**
- Added user avatar component to full tweet display
- Displayed full name and username
- Converted timestamp to relative time (e.g., "20h")
- Added "more options" button
- Implemented hover/active effects on avatar and name
- Made the name clickable to navigate to profile
- Added replies functionality

**Ammar Yasser**
- Planned page structure and sub-issues for Messages Page
- Defined reusable UI components (Conversation Item, Chat Window, What's Happening)
- Implemented responsive layout for Messages Page (two-column: conversation list + chat window)
- Built Conversation List Sidebar with avatars, names, and previews
- Performed unit testing for layout and UI components to ensure consistent rendering and responsiveness
- Enhanced Left Sidebar responsiveness by adding a Bottom Sidebar for mobile view (icon-only navigation)

**Yousef Adel**
- Created a reusable UI component called Switcher
- Completed Poll feature inside Add Tweet with state management
- Added red color indicator when reaching max word limit while typing
- Built a Menu component reusable for Reply options and Grok options
- Implemented Reply options with full state handling
- Working on the Schedule component for scheduling tweets

## Backend Team

**Omar Nabil (Sub Team Leader)**
- Attended weekly meeting
- Implemented Follow/Unfollow users functionality
- Implemented Block/Unblock users functionality
- Implemented Get Followers/Following/Blocks endpoints

**Mohamed Sameh**
- Implemented Google & Github OAuth authentication
- Implemented Reset & Forget Password functionality
- Handled email verification tokens using Redis
- Added Google reCAPTCHA integration
- Integrated authentication features with frontend

**Yousef Mostafa**
- Implemented Get List of likers and reposters
- Implemented on Like and unlike functionality
- Implemented on Liked posts feature
- Implemented on Hashtags implementation

**Ahmed Gamal**
- Implemented Get current user profile endpoint
- Implemented Get user profile by id/username endpoint
- Implemented Update current user profile endpoint
- Implemented Search user profiles using username/name functionality

**Salah Mostafa**
- Implemented Timeline: get tweets for home feed
- Conducted research on how to implement Explore feature using Machine Learning

## Cross-Platform Team

**Ziad Montaser (Sub Team Leader)**
- Implemented Direct Messages Screen
- Implemented Chatting Screen
- Discussed Phase 1 requirements
- Conducted Sprint Planning Meeting

**Hossam Mohamed**
- Continued learning Flutter with practical exercises
- Learning Riverpod and began practice implementation
- Finished sprint requirement and created profile summary widget
- Finished Button widget to be reused across the application
- Conducted prospective meetings to discuss the first sprint

**Farouk Mohamed**
- Studied Freezed for state management
- Implemented UI state management
- Integrated with backend API for registration flow
- Integrated with backend API for logging in a new user

**Mazen Hassan**
- Applied MVVM Architecture on Tweet component
- Finished Initial Design on Detailed Tweet
- Made a StandUp Meeting for next Sprint Planning
- Created MockData and MockServer for Testing Tweet Media and Body

**Mohamed Yasser**
- Understanding and applying Riverpod state management
- Applied MVVM architecture and separated each part
- Learning advanced concepts like go router and Riverpod @freezed
- Finished the main settings page
- Finished the UI of the account settings page
- Made important widgets and styles to be used throughout the project
- Working on privacy settings
- Working on search functionality for the settings

## DevOps Team

**Karim Farid (Team Leader)**
- Set up a full CI/CD pipeline for the backend
- Configured automated image builds on push to dev branch, pushing to Docker Hub and GitHub Container Registry
- Used Helm to deploy updated images to Azure infrastructure
- Created dev infrastructure using Terraform
- Deployed PostgreSQL database
- Set up Ingress NGINX with subdomains to reduce costs (single Load Balancer)
- Created Kubernetes cluster for dev environment
- Provided backend API access for the frontend team
- Started work on Blob (S3-like) media storage setup
- Deployed frontend for dev environment

## Testing Team

**Mohamed Ayman Mohamed (Sub Team Leader)**
- Created login test cases to ensure proper authentication functionality
- Attended a meeting with leader and sub-team leaders to review progress and discuss the 20% deliverable planned for Week 7
- Learning Flutter integration testing for end-to-end (E2E) testing of the Flutter application

**Ahmed Fouad Fouad**
- Prepared test cases for adding and getting tweets
- Prepared media tests for image and videos uploadingv
