-- ==============================================================================
-- AI Research Lab: Supabase PostgreSQL Schema & Row Level Security (RLS)
-- ==============================================================================

-- Enable UUID extension if not enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Profiles Table (Synced from Supabase auth.users)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. Projects Table
CREATE TABLE IF NOT EXISTS public.projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    research_question TEXT,
    domain TEXT,
    description TEXT,
    created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 3. Project Members Table (Roles: owner, researcher, viewer)
CREATE TABLE IF NOT EXISTS public.project_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'researcher', 'viewer')),
    joined_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(project_id, user_id)
);

-- 4. Papers Table (Saved literature per project)
CREATE TABLE IF NOT EXISTS public.papers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    authors JSONB DEFAULT '[]'::jsonb,
    abstract TEXT,
    year INTEGER,
    venue TEXT,
    doi TEXT,
    arxiv_id TEXT,
    open_access_pdf_url TEXT,
    storage_path TEXT,
    added_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 5. Research Notes Table
CREATE TABLE IF NOT EXISTS public.research_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 6. Paper Annotations Table (Highlights & Marginalia)
CREATE TABLE IF NOT EXISTS public.paper_annotations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id UUID NOT NULL REFERENCES public.papers(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    selected_text TEXT NOT NULL,
    comment TEXT,
    color TEXT DEFAULT '#F59E0B',
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 7. Knowledge Nodes Table (Entities, Methods, Datasets, Concepts)
CREATE TABLE IF NOT EXISTS public.knowledge_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('method', 'dataset', 'task', 'metric', 'concept')),
    description TEXT,
    source_paper_ids JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(project_id, name)
);

-- 8. Knowledge Edges Table (Relational Connections)
CREATE TABLE IF NOT EXISTS public.knowledge_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    source_node_id UUID NOT NULL REFERENCES public.knowledge_nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES public.knowledge_nodes(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    evidence TEXT,
    source_paper_id UUID REFERENCES public.papers(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(project_id, source_node_id, target_node_id, relation_type)
);



-- ==============================================================================
-- Automatic Triggers
-- ==============================================================================

-- Trigger: Automatically handle profile creation on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name, avatar_url)
    VALUES (
        new.id,
        new.email,
        COALESCE(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)),
        new.raw_user_meta_data->>'avatar_url'
    )
    ON CONFLICT (id) DO UPDATE
    SET email = EXCLUDED.email,
        full_name = COALESCE(EXCLUDED.full_name, public.profiles.full_name);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT OR UPDATE ON auth.users
    FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();

-- ==============================================================================
-- Row-Level Security (RLS) Policies
-- ==============================================================================

-- Enable RLS on all tables
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.project_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.papers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.research_notes ENABLE ROW LEVEL SECURITY;

-- Helper function: Check if user is member of a project
CREATE OR REPLACE FUNCTION public.is_project_member(_project_id UUID, _user_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM public.project_members
        WHERE project_id = _project_id AND user_id = _user_id
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Helper function: Check user role in project
CREATE OR REPLACE FUNCTION public.get_project_role(_project_id UUID, _user_id UUID)
RETURNS TEXT AS $$
DECLARE
    _role TEXT;
BEGIN
    SELECT role INTO _role FROM public.project_members
    WHERE project_id = _project_id AND user_id = _user_id;
    RETURN _role;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Profiles Policies
CREATE POLICY "Public profiles are viewable by authenticated users"
    ON public.profiles FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "Users can update their own profile"
    ON public.profiles FOR UPDATE
    TO authenticated
    USING (auth.uid() = id);

-- Projects Policies
CREATE POLICY "Users can view projects they are members of"
    ON public.projects FOR SELECT
    TO authenticated
    USING (public.is_project_member(id, auth.uid()));

CREATE POLICY "Users can create projects"
    ON public.projects FOR INSERT
    TO authenticated
    WITH CHECK (auth.uid() = created_by);

CREATE POLICY "Owners and Researchers can update projects"
    ON public.projects FOR UPDATE
    TO authenticated
    USING (public.get_project_role(id, auth.uid()) IN ('owner', 'researcher'));

CREATE POLICY "Only Owners can delete projects"
    ON public.projects FOR DELETE
    TO authenticated
    USING (public.get_project_role(id, auth.uid()) = 'owner');

-- Project Members Policies
CREATE POLICY "Users can view members of their projects"
    ON public.project_members FOR SELECT
    TO authenticated
    USING (public.is_project_member(project_id, auth.uid()));

CREATE POLICY "Owners can add members to their projects"
    ON public.project_members FOR INSERT
    TO authenticated
    WITH CHECK (
        public.get_project_role(project_id, auth.uid()) = 'owner'
        OR auth.uid() = user_id -- Allow creator to add self on project creation
    );

CREATE POLICY "Owners can update member roles"
    ON public.project_members FOR UPDATE
    TO authenticated
    USING (public.get_project_role(project_id, auth.uid()) = 'owner');

CREATE POLICY "Owners can remove members"
    ON public.project_members FOR DELETE
    TO authenticated
    USING (public.get_project_role(project_id, auth.uid()) = 'owner');

-- Papers Policies
CREATE POLICY "Project members can view saved papers"
    ON public.papers FOR SELECT
    TO authenticated
    USING (public.is_project_member(project_id, auth.uid()));

CREATE POLICY "Owners and Researchers can add papers"
    ON public.papers FOR INSERT
    TO authenticated
    WITH CHECK (public.get_project_role(project_id, auth.uid()) IN ('owner', 'researcher'));

CREATE POLICY "Owners and Researchers can delete papers"
    ON public.papers FOR DELETE
    TO authenticated
    USING (public.get_project_role(project_id, auth.uid()) IN ('owner', 'researcher'));

-- Research Notes Policies
CREATE POLICY "Project members can view research notes"
    ON public.research_notes FOR SELECT
    TO authenticated
    USING (public.is_project_member(project_id, auth.uid()));

CREATE POLICY "Owners and Researchers can create research notes"
    ON public.research_notes FOR INSERT
    TO authenticated
    WITH CHECK (public.get_project_role(project_id, auth.uid()) IN ('owner', 'researcher'));

CREATE POLICY "Owners and Researchers can update research notes"
    ON public.research_notes FOR UPDATE
    TO authenticated
    USING (public.get_project_role(project_id, auth.uid()) IN ('owner', 'researcher'));

CREATE POLICY "Owners and Researchers can delete research notes"
    ON public.research_notes FOR DELETE
    TO authenticated
    USING (public.get_project_role(project_id, auth.uid()) IN ('owner', 'researcher'));

-- Paper Annotations Policies
CREATE POLICY "Project members can view paper annotations"
    ON public.paper_annotations FOR SELECT
    TO authenticated
    USING (public.is_project_member(project_id, auth.uid()));

CREATE POLICY "Owners and Researchers can add paper annotations"
    ON public.paper_annotations FOR INSERT
    TO authenticated
    WITH CHECK (public.get_project_role(project_id, auth.uid()) IN ('owner', 'researcher'));

CREATE POLICY "Owners and Researchers can delete paper annotations"
    ON public.paper_annotations FOR DELETE
    TO authenticated
    USING (public.get_project_role(project_id, auth.uid()) IN ('owner', 'researcher'));

-- Knowledge Nodes Policies
ALTER TABLE public.knowledge_nodes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Project members can view knowledge nodes"
    ON public.knowledge_nodes FOR SELECT
    TO authenticated
    USING (public.is_project_member(project_id, auth.uid()));

CREATE POLICY "Owners and Researchers can insert knowledge nodes"
    ON public.knowledge_nodes FOR INSERT
    TO authenticated
    WITH CHECK (public.get_project_role(project_id, auth.uid()) IN ('owner', 'researcher'));

CREATE POLICY "Owners and Researchers can delete knowledge nodes"
    ON public.knowledge_nodes FOR DELETE
    TO authenticated
    USING (public.get_project_role(project_id, auth.uid()) IN ('owner', 'researcher'));

-- Knowledge Edges Policies
ALTER TABLE public.knowledge_edges ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Project members can view knowledge edges"
    ON public.knowledge_edges FOR SELECT
    TO authenticated
    USING (public.is_project_member(project_id, auth.uid()));

CREATE POLICY "Owners and Researchers can insert knowledge edges"
    ON public.knowledge_edges FOR INSERT
    TO authenticated
    WITH CHECK (public.get_project_role(project_id, auth.uid()) IN ('owner', 'researcher'));

CREATE POLICY "Owners and Researchers can delete knowledge edges"
    ON public.knowledge_edges FOR DELETE
    TO authenticated
    USING (public.get_project_role(project_id, auth.uid()) IN ('owner', 'researcher'));

