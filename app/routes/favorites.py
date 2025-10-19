"""
Favorites routes
"""
from fastapi import APIRouter, HTTPException, Depends, status
from app.database import supabase_admin
from app.middleware.auth import get_current_tenant
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/favorites")


class FavoriteCreate(BaseModel):
    property_id: str


@router.get("/")
async def get_favorites(current_user: dict = Depends(get_current_tenant)):
    """
    Get user's favorite properties (tenants only)
    """
    try:
        tenant_id = current_user["id"]
        
        # Fetch favorites with property details
        response = supabase_admin.table("favorites").select(
            "*, property:properties(*, landlord:users!landlord_id(id, full_name, avatar_url, trust_score, verification_status))"
        ).eq("tenant_id", tenant_id).order("created_at", desc=True).execute()
        
        # Format response
        favorites = []
        for fav in response.data:
            property_data = fav.get("property")
            if property_data:
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
                property_data['is_favorited'] = True
                favorites.append(property_data)
        
        return {
            "success": True,
            "favorites": favorites,
            "count": len(favorites)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch favorites: {str(e)}"
        )


@router.post("/")
async def add_favorite(
    favorite_data: FavoriteCreate,
    current_user: dict = Depends(get_current_tenant)
):
    """
    Add property to favorites (tenants only)
    """
    try:
        tenant_id = current_user["id"]
        property_id = favorite_data.property_id
        
        # Check if property exists
        property_check = supabase_admin.table("properties").select("id").eq(
            "id", property_id
        ).single().execute()
        
        if not property_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Property not found"
            )
        
        # Check if already favorited
        existing_fav = supabase_admin.table("favorites").select("*").eq(
            "tenant_id", tenant_id
        ).eq("property_id", property_id).execute()
        
        if existing_fav.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Property already in favorites"
            )
        
        # Add to favorites
        fav_dict = {
            "tenant_id": tenant_id,
            "property_id": property_id
        }
        
        response = supabase_admin.table("favorites").insert(fav_dict).execute()
        
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to add favorite"
            )
        
        # Increment favorite count on property
        property_data = supabase_admin.table("properties").select("favorite_count").eq(
            "id", property_id
        ).single().execute()
        
        supabase_admin.table("properties").update({
            "favorite_count": property_data.data.get("favorite_count", 0) + 1
        }).eq("id", property_id).execute()
        
        return {
            "success": True,
            "message": "Property added to favorites",
            "favorite": response.data[0]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to add favorite: {str(e)}"
        )


@router.delete("/{property_id}")
async def remove_favorite(
    property_id: str,
    current_user: dict = Depends(get_current_tenant)
):
    """
    Remove property from favorites (tenants only)
    """
    try:
        tenant_id = current_user["id"]
        
        # Check if favorited
        existing_fav = supabase_admin.table("favorites").select("*").eq(
            "tenant_id", tenant_id
        ).eq("property_id", property_id).execute()
        
        if not existing_fav.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Favorite not found"
            )
        
        # Remove from favorites
        supabase_admin.table("favorites").delete().eq(
            "tenant_id", tenant_id
        ).eq("property_id", property_id).execute()
        
        # Decrement favorite count on property
        property_data = supabase_admin.table("properties").select("favorite_count").eq(
            "id", property_id
        ).single().execute()
        
        if property_data.data:
            supabase_admin.table("properties").update({
                "favorite_count": max(0, property_data.data.get("favorite_count", 0) - 1)
            }).eq("id", property_id).execute()
        
        return {
            "success": True,
            "message": "Property removed from favorites"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to remove favorite: {str(e)}"
        )
