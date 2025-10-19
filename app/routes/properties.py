"""
Property routes
"""
from fastapi import APIRouter, HTTPException, Depends, Query, status
from app.models.property import PropertyCreate, PropertyUpdate, PropertyResponse, PropertyListResponse, PropertySearch
from app.database import supabase_admin
from app.middleware.auth import get_current_user, get_current_landlord, get_optional_current_user
from typing import Optional
from datetime import datetime
import math

router = APIRouter(prefix="/properties")


@router.get("/search")
async def search_properties(
    location: Optional[str] = Query(None),
    min_budget: Optional[float] = Query(None, ge=0),
    max_budget: Optional[float] = Query(None, ge=0),
    bedrooms: Optional[int] = Query(None, ge=0),
    bathrooms: Optional[int] = Query(None, ge=1),
    property_type: Optional[str] = Query(None),
    sort: str = Query("newest", regex="^(newest|price_low|price_high)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[dict] = Depends(get_optional_current_user)
):
    """
    Search properties with filters and pagination
    """
    try:
        # Build query
        query = supabase_admin.table("properties").select(
            "*, landlord:users!landlord_id(id, full_name, avatar_url, trust_score, verification_status)",
            count="exact"
        ).eq("status", "active").is_("deleted_at", "null")
        
        # Apply filters
        if location:
            query = query.ilike("location", f"%{location}%")
        
        if min_budget:
            query = query.gte("", min_budget)
        rent_amount
        if max_budget:
            query = query.lte("rent_amount", max_budget)
        
        if bedrooms:
            query = query.eq("bedrooms", bedrooms)
        
        if bathrooms:
            query = query.gte("bathrooms", bathrooms)
        
        if property_type:
            query = query.eq("property_type", property_type)
        
        # Apply sorting
        if sort == "newest":
            query = query.order("created_at", desc=True)
        elif sort == "price_low":
            query = query.order("rent_amount", desc=False)
        elif sort == "price_high":
            query = query.order("rent_amount", desc=True)
        
        # Apply pagination
        offset = (page - 1) * limit
        query = query.range(offset, offset + limit - 1)
        
        # Execute query
        response = query.execute()
        
        # Calculate pagination
        total = response.count if hasattr(response, 'count') else len(response.data)
        total_pages = math.ceil(total / limit) if total > 0 else 1
        
        # Format properties
        properties = []
        for prop in response.data:
            landlord_data = prop.pop('landlord', None)
            property_dict = {**prop}
            
            if landlord_data:
                property_dict['landlord'] = {
                    'id': landlord_data['id'],
                    'name': landlord_data.get('full_name'),
                    'avatar_url': landlord_data.get('avatar_url'),
                    'trust_score': landlord_data.get('trust_score', 50),
                    'verified': landlord_data.get('verification_status') == 'approved',
                    'properties_count': 0,
                    'joined_year': datetime.now().year,
                    'guarantee_joined': False
                }
            
            properties.append(property_dict)
        
        return {
            "success": True,
            "properties": properties,
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.post("/", response_model=PropertyResponse)
async def create_property(
    property_data: PropertyCreate,
    current_user: dict = Depends(get_current_landlord)
):
    """
    Create a new property listing (landlords only)
    """
    try:
        landlord_id = current_user["id"]
        
        # Prepare property data
        property_dict = property_data.dict()
        property_dict["landlord_id"] = landlord_id
        property_dict["agency_fee"] = 0  # Nulo's unique feature!
        property_dict["view_count"] = 0
        property_dict["favorite_count"] = 0
        property_dict["application_count"] = 0
        property_dict["verified"] = False
        
        # Insert property
        response = supabase_admin.table("properties").insert(property_dict).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create property"
            )
        
        property_result = response.data[0]
        
        # Fetch landlord info
        landlord_response = supabase_admin.table("users").select(
            "id, full_name, avatar_url, trust_score, verification_status"
        ).eq("id", landlord_id).single().execute()
        
        landlord_data = landlord_response.data
        property_result['landlord'] = {
            'id': landlord_data['id'],
            'name': landlord_data.get('full_name'),
            'avatar_url': landlord_data.get('avatar_url'),
            'trust_score': landlord_data.get('trust_score', 50),
            'verified': landlord_data.get('verification_status') == 'approved',
            'properties_count': 1,
            'joined_year': datetime.now().year,
            'guarantee_joined': False
        }
        
        return property_result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create property: {str(e)}"
        )


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: str,
    current_user: Optional[dict] = Depends(get_optional_current_user)
):
    """
    Get property details by ID
    """
    try:
        # Fetch property with landlord info
        response = supabase_admin.table("properties").select(
            "*, landlord:users!landlord_id(id, full_name, avatar_url, trust_score, verification_status)"
        ).eq("id", property_id).is_("deleted_at", "null").single().execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Property not found"
            )
        
        property_data = response.data
        
        # Increment view count
        supabase_admin.table("properties").update({
            "view_count": property_data.get("view_count", 0) + 1
        }).eq("id", property_id).execute()
        
        # Format landlord data
        landlord_data = property_data.pop('landlord', None)
        if landlord_data:
            property_data['landlord'] = {
                'id': landlord_data['id'],
                'name': landlord_data.get('full_name'),
                'avatar_url': landlord_data.get('avatar_url'),
                'trust_score': landlord_data.get('trust_score', 50),
                'verified': landlord_data.get('verification_status') == 'approved',
                'properties_count': 0,
                'joined_year': datetime.now().year,
                'guarantee_joined': False
            }
        
        # Check if favorited by current user
        property_data['is_favorited'] = False
        if current_user:
            fav_check = supabase_admin.table("favorites").select("*").eq(
                "tenant_id", current_user["id"]
            ).eq("property_id", property_id).execute()
            property_data['is_favorited'] = len(fav_check.data) > 0
        
        return property_data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch property: {str(e)}"
        )


@router.patch("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: str,
    property_data: PropertyUpdate,
    current_user: dict = Depends(get_current_landlord)
):
    """
    Update property (landlord only, own properties)
    """
    try:
        landlord_id = current_user["id"]
        
        # Verify ownership
        property_check = supabase_admin.table("properties").select("landlord_id").eq(
            "id", property_id
        ).single().execute()
        
        if not property_check.data or property_check.data["landlord_id"] != landlord_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this property"
            )
        
        # Update property
        update_dict = property_data.dict(exclude_unset=True)
        response = supabase_admin.table("properties").update(update_dict).eq(
            "id", property_id
        ).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update property"
            )
        
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update property: {str(e)}"
        )


@router.delete("/{property_id}")
async def delete_property(
    property_id: str,
    current_user: dict = Depends(get_current_landlord)
):
    """
    Delete property (soft delete - landlord only, own properties)
    """
    try:
        landlord_id = current_user["id"]
        
        # Verify ownership
        property_check = supabase_admin.table("properties").select("landlord_id").eq(
            "id", property_id
        ).single().execute()
        
        if not property_check.data or property_check.data["landlord_id"] != landlord_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this property"
            )
        
        # Soft delete
        supabase_admin.table("properties").update({
            "deleted_at": datetime.now().isoformat(),
            "status": "inactive"
        }).eq("id", property_id).execute()
        
        return {
            "success": True,
            "message": "Property deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete property: {str(e)}"
        )
